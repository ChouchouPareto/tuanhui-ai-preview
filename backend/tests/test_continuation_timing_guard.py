import json
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.config import settings
from app.models import ModelCallRecord, IntakeRunLock, WorkflowTask, WorkflowEvent, TaskStatus, utc_now
from app.services import intake_understanding, text_guard
from app.services.model_gateway import ModelGatewayError
from app.services.telemetry import emit, estimate
from test_m1_creations import setup_creation, submit, confirm


def test_changed_message_after_timeout_is_not_locked(client, monkeypatch):
    monkeypatch.setattr(settings, "dashscope_api_key", "test")
    calls = []
    def model(*args):
        calls.append(1)
        if len(calls) == 1:
            raise ModelGatewayError("MODEL_TIMEOUT", "timeout")
        return '{"facts":{},"uncertain_fields":[]}', {}, 12
    monkeypatch.setattr(intake_understanding, "_post_chat", model)
    _, asset, base = setup_creation(client)
    args = dict(use_ai=True, accepted_understanding_policy="text-understanding-paid-v1", input_mode="chat")
    assert submit(client, base, asset, **args).status_code == 409
    assert submit(client, base, asset, **args).status_code == 409
    assert len(calls) == 1
    changed = submit(client, base, asset, text="店名：山西面馆，做五图", **args)
    assert changed.status_code == 200, changed.text
    assert len(calls) == 2
    with SessionLocal() as db:
        assert all(r.duration_ms > 0 for r in db.scalars(select(ModelCallRecord)))
        assert db.scalar(select(IntakeRunLock)).task_id is None
    activity = client.get(base + "/activity").json()
    assert activity["current"]["state"] == "completed"
    assert len(activity["spans"]) == 2


def test_continuation_inherits_context_and_preserves_parent(client):
    project, asset, base = setup_creation(client)
    original = submit(client, base, asset, input_mode="chat").json()
    task_id = confirm(client, base, original).json()["task_id"]
    child = client.post(f"/api/v1/projects/{project}/creations", json={"parent_creation_id": original["creation_id"]}).json()
    child_base = f"/api/v1/projects/{project}/creations/{child['creation_id']}"
    changed = submit(client, child_base, asset, input_mode="chat", text="换一个清爽的风格").json()
    assert changed["snapshot"]["facts"]["store_name"] == "测试店"
    assert len(changed["snapshot"]["messages"]) == 4
    assert client.get(child_base + "/review").json()["previous_task_id"] == task_id
    assert client.get(base + "/review").json()["snapshot"] == original["snapshot"]
    other, _, _ = setup_creation(client)
    assert client.post(f"/api/v1/projects/{other}/creations", json={"parent_creation_id": original["creation_id"]}).status_code == 404


def test_stale_guard_releases_without_retry(client, monkeypatch):
    project, _, base = setup_creation(client)
    with SessionLocal() as db:
        task = WorkflowTask(project_id=project, task_type="intake_understanding", status=TaskStatus.RUNNING,
            created_at=utc_now()-timedelta(hours=1), result={"creation_id":base.split("/")[-1]})
        db.add(task); db.flush()
        db.add(IntakeRunLock(creation_id=base.split("/")[-1], task_id=task.id)); db.commit()
        monkeypatch.setattr(intake_understanding, "_post_chat", lambda *a: pytest.fail("no retry"))
        assert intake_understanding.recover_stale_understanding(db) == 1
        assert task.status == TaskStatus.NEEDS_USER
        assert db.scalar(select(IntakeRunLock)).task_id is None


def test_eta_requires_comparable_success_samples(client):
    project, _, _ = setup_creation(client)
    with SessionLocal() as db:
        for i in range(4):
            emit(db, project, str(i), "generation", "completed", model="cohort-a", duration_ms=1000+i*1000)
        assert estimate(db,"generation","cohort-a")["range_ms"] is None
        emit(db, project, "failure", "generation", "failed", model="cohort-a", duration_ms=90000)
        emit(db, project, "other", "generation", "completed", model="cohort-b", duration_ms=90000)
        assert estimate(db,"generation","cohort-a")["range_ms"] is None
        emit(db, project, "fifth", "generation", "completed", model="cohort-a", duration_ms=5000)
        assert estimate(db,"generation","cohort-a")["range_ms"] == [3000,5000]


def test_text_guard_blocks_double_typography_and_retains_audit(tmp_path, monkeypatch):
    from app.services.design_plan import build_design_plan
    from app.services.image_generation import render_and_slice, build_visual_prompt
    from PIL import Image
    import io
    monkeypatch.setattr(text_guard,"detect_text",lambda p:[{"text":"山西面馆","confidence":.99,"box":[.3,.3,.4,.2]}])
    plan = build_design_plan({"store_name":"山西面馆", "hero_price":"99元"})
    plan["render_mode"] = "illustration"
    assert "山西面馆" not in build_visual_prompt(plan)
    assert "99元" not in build_visual_prompt(plan)
    raw = io.BytesIO(); Image.new("RGB", (2000,300)).save(raw,"PNG")
    with pytest.raises(ValueError, match="重复排字"):
        render_and_slice(raw.getvalue(),plan,tmp_path)
    assert (tmp_path/"model-visual.png").exists()
    assert json.loads((tmp_path/"text-guard.json").read_text())["status"] == "rejected"
    assert not (tmp_path/"long.png").exists()


def test_text_guard_fails_closed_on_detector_error(tmp_path, monkeypatch):
    monkeypatch.setattr(text_guard,"detect_text",lambda p: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(ValueError, match="未自动重新生图"):
        text_guard.check_background(tmp_path/"input.png")
