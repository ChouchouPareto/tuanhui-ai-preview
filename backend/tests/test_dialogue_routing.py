import json

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Creation, CreationConfirmation, DialogueTurn, IntakeRevision, ModelCallRecord, TaskStatus, WorkflowTask
from app.services.dialogue_routing import decide
from app.services.intake import digest
from test_m1_creations import setup_creation, submit, confirm


def finished(client):
    project, asset, base = setup_creation(client)
    draft = submit(client, base, asset, input_mode="chat").json()
    task_id = confirm(client, base, draft).json()["task_id"]
    with SessionLocal() as db:
        task = db.get(WorkflowTask, task_id)
        task.status = TaskStatus.SUCCEEDED
        task.progress = 100
        db.commit()
    return project, asset, base, draft, task_id


@pytest.mark.parametrize("message", [
    "文字又重叠了", "为什么还是这样？", "别重新生成，只说明原因", "不行", "图片打不开",
    "这图太丑了，帮我看看", "这个问题给我解释", "生成失败了", "图不对，帮我修好",
    "不要重做，我只是想问一下", "停止生成", "还要多久？", "用了哪个模型，花多久？",
    "这张标题大一点", "价格改成68元，其他别动", "再来一下", "只改第二张的画面",
])
def test_feedback_never_creates_generation_or_mutates_original(client, monkeypatch, message):
    project, _, base, draft, task_id = finished(client)
    from app.services import model_gateway, intake_understanding
    def forbidden(*args, **kwargs):
        pytest.fail("feedback must not call any provider")
    monkeypatch.setattr(model_gateway, "_post_chat", forbidden)
    monkeypatch.setattr(intake_understanding, "understand", forbidden)
    before = client.get(base + "/review").json()
    response = client.post("/api/v1/dialogue/route", json={"project_id": project, "creation_id": draft["creation_id"], "text": message})
    assert response.status_code == 200, response.text
    assert response.json()["can_prepare"] is False
    assert response.json()["model_calls"] == 0
    assert response.json()["target"]["task_id"] == task_id
    assert client.get(base + "/review").json() == before
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Creation)) == 1
        assert db.scalar(select(func.count()).select_from(WorkflowTask)) == 1
        assert db.scalar(select(func.count()).select_from(ModelCallRecord)) == 0
        assert db.get(WorkflowTask, task_id).status == TaskStatus.SUCCEEDED
    history = client.get("/api/v1/dialogue/history", params={"project_id": project, "creation_id": draft["creation_id"]}).json()
    assert history[-1]["text"] == message


def test_backend_intake_and_legacy_confirm_both_guard_feedback(client, monkeypatch):
    project, asset, base, original, _ = finished(client)
    child = client.post(f"/api/v1/projects/{project}/creations", json={"parent_creation_id": original["creation_id"]}).json()
    child_base = f"/api/v1/projects/{project}/creations/{child['creation_id']}"
    from app.services import intake_understanding
    monkeypatch.setattr(intake_understanding, "understand", lambda *a: pytest.fail("must guard before model"))
    response = submit(client, child_base, asset, text="文字又重叠了", input_mode="chat", use_ai=True, accepted_understanding_policy="text-understanding-paid-v1")
    assert response.status_code == 409
    assert "DIALOGUE_ACTION_REQUIRED" in response.text
    # Simulate a ready legacy draft created by the old client before this fix.
    with SessionLocal() as db:
        creation = db.get(Creation, child["creation_id"])
        snap = {**original["snapshot"], "parent_creation_id": original["creation_id"], "messages": [{"role": "user", "content": "为什么这样，检查一下"}]}
        row = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation.id))
        row.revision = 1
        row.snapshot, row.snapshot_hash = snap, digest(snap)
        creation.revision, creation.status = 1, "READY_TO_CONFIRM"
        db.commit()
    review = client.get(child_base + "/review").json()
    response = confirm(client, child_base, review)
    assert response.status_code == 409
    assert "DIALOGUE_ACTION_REQUIRED" in response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CreationConfirmation)) == 1


@pytest.mark.parametrize("mode", ["chat", "merge", "replace", "reply"])
def test_old_input_modes_cannot_bypass_feedback_guard(client, mode):
    _, asset, base = setup_creation(client)
    result = submit(client, base, asset, text="为什么文字重叠了", input_mode=mode)
    assert result.status_code == 409
    assert "DIALOGUE_ACTION_REQUIRED" in result.text


def test_inspection_uses_saved_evidence_not_guessed_cause(client):
    project, _, _, draft, task_id = finished(client)
    folder = settings.generated_dir / project / task_id
    folder.mkdir(parents=True)
    (folder / "model-visual.png").write_bytes(b"fixture; not decoded by the inspector")
    (folder / "text-guard.json").write_text(json.dumps({"status": "rejected"}), encoding="utf-8")
    response = client.post("/api/v1/dialogue/route", json={"project_id": project, "creation_id": draft["creation_id"], "text": "为什么叠字？"}).json()
    assert "底图里已经出现文字" in response["reply"]
    assert {"kind": "text_guard", "status": "rejected"} in response["evidence"]
    (folder / "text-guard.json").write_text("broken", encoding="utf-8")
    response = client.post("/api/v1/dialogue/route", json={"project_id": project, "task_id": task_id, "text": "为什么叠字？"}).json()
    assert "还缺少" in response["reply"]
    assert "底图里已经出现文字" not in response["reply"]


def test_cross_project_and_mismatched_targets_are_rejected(client):
    project, _, _, draft, task_id = finished(client)
    other, _, _, other_draft, other_task = finished(client)
    for payload in [
        {"project_id": other, "creation_id": draft["creation_id"]},
        {"project_id": other, "task_id": task_id},
        {"project_id": project, "creation_id": draft["creation_id"], "task_id": other_task},
    ]:
        response = client.post("/api/v1/dialogue/route", json={**payload, "text": "看看这版"})
        assert response.status_code in {404, 409}
    assert client.get("/api/v1/dialogue/history", params={"project_id": other, "task_id": task_id}).status_code == 404


def test_running_queries_and_failed_tasks_do_not_resubmit(client):
    project, _, _, draft, task_id = finished(client)
    for state in [TaskStatus.RUNNING, TaskStatus.NEEDS_USER, TaskStatus.FAILED_FINAL]:
        with SessionLocal() as db:
            task = db.get(WorkflowTask, task_id)
            task.status = state
            task.error_code = "MODEL_RESULT_UNKNOWN"
            db.commit()
        result = client.post("/api/v1/dialogue/route", json={"project_id": project, "task_id": task_id, "text": "还要多久？"}).json()
        assert not result["can_prepare"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(WorkflowTask)) == 1


def test_explicit_new_generation_and_title_edit_can_prepare_but_do_not_execute(client):
    project, _, _, draft, _ = finished(client)
    for message in ["重新生成一版清爽的", "换一个清爽的风格", "标题改成今天吃碗面", "标题改成今晚吃什么？"]:
        result = client.post("/api/v1/dialogue/route", json={"project_id": project, "creation_id": draft["creation_id"], "text": message}).json()
        assert result["can_prepare"], (message, result)
        assert result["action"] == "prepare"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(WorkflowTask)) == 1


def test_fresh_compose_does_not_accidentally_target_old_task(client):
    project, _, _, _, _ = finished(client)
    result = client.post("/api/v1/dialogue/route", json={"project_id": project, "new_session": True, "text": "山西面馆"}).json()
    assert result["can_prepare"] and result["target"]["task_id"] is None


@pytest.mark.parametrize("message", ["袁记云饺", "山西面馆，五图", "给门店做一套团购宣传图", ""])
def test_first_input_does_not_require_a_prompt_template(client, message):
    result = client.post("/api/v1/dialogue/route", json={"text": message}).json()
    assert result["can_prepare"]


@pytest.mark.parametrize("message", ["你好", "全案包括什么？", "千问和另一个模型有什么不同？", "不要重新生成，告诉我原因"])
def test_questions_before_project_creation_are_not_generation(client, message):
    result = client.post("/api/v1/dialogue/route", json={"text": message}).json()
    assert not result["can_prepare"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Creation)) == 0


@pytest.mark.parametrize("message", [
    "删除这个项目", "确认删除当前项目", "帮我打开昨天那版", "导出五张上传用的图片",
    "识别这张门头上的店名", "提取这张菜单的菜名", "把那个项目的图拿过来",
    "用这个菜品图", "就用刚才的店名", "两张详情别做一样的",
])
def test_first_turn_non_generation_actions_cannot_become_fresh_intake(client, message):
    result = client.post("/api/v1/dialogue/route", json={"text": message}).json()
    assert result["can_prepare"] is False
    assert result["action"] == "clarify"
    assert result["model_calls"] == 0
    from app.services.dialogue_routing import guard_intake_message
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        guard_intake_message(message, has_result=False)


def test_old_selected_task_is_not_replaced_by_latest(client):
    project, _, _, _, old_id = finished(client)
    with SessionLocal() as db:
        other = WorkflowTask(project_id=project, task_type="group_buying_image_generation", status=TaskStatus.SUCCEEDED)
        db.add(other)
        db.commit()
    result = client.post("/api/v1/dialogue/route", json={"project_id": project, "task_id": old_id, "text": "这版有问题"}).json()
    assert result["target"]["task_id"] == old_id
    ambiguous = client.post("/api/v1/dialogue/route", json={"project_id": project, "text": "这张不行"}).json()
    assert ambiguous["action"] == "clarify"
    assert not ambiguous["can_prepare"]


def test_local_only_cannot_fall_back_to_paid_understanding_or_generation(client, monkeypatch):
    project, asset, _, parent, _ = finished(client)
    child = client.post(f"/api/v1/projects/{project}/creations", json={"parent_creation_id": parent["creation_id"]}).json()
    base = f"/api/v1/projects/{project}/creations/{child['creation_id']}"
    from app.services import intake_understanding
    monkeypatch.setattr(intake_understanding, "understand", lambda *a: pytest.fail("local-only must not call model"))
    changed_style = submit(client, base, asset, text="标题改成今天吃面", input_mode="chat", style="minimal", local_only=True,
        use_ai=True, accepted_understanding_policy="text-understanding-paid-v1")
    assert changed_style.status_code == 409 and "LOCAL_EDIT_UNAVAILABLE" in changed_style.text
    same_style = submit(client, base, asset, text="标题改成今天吃面", input_mode="chat", local_only=True)
    assert same_style.status_code == 200, same_style.text
    assert same_style.json()["snapshot"]["copy_edit"] == "今天吃面"
