"""Offline regressions derived from the three-entry audit. No paid calls."""
import io
import json

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import DesignPlan, ModelCallRecord, WorkflowTask
from app.services.design_plan import build_design_plan
from app.services.image_generation import build_visual_prompt, render_and_slice, save_generation_request
from app.services.output_contract import detect_output
from test_m1_creations import setup_creation, submit, confirm


@pytest.mark.parametrize("text,fallback,expected", [
    ("做五连图，左上角放logo", "five_panel", "five_panel"),
    ("做全案，包含五连图、代金券和logo", "full_plan", "full_plan"),
    ("参考这张代金券的配色", "five_panel", "five_panel"),
    ("参考logo", "three_panel", "three_panel"),
    ("不要三连图，改成五连图", "three_panel", "five_panel"),
    ("改成三连图，保留logo", "five_panel", "three_panel"),
    ("logo", "five_panel", "logo"),
    ("山西面馆五图", "three_panel", "five_panel"),
    ("做一张封面图", "five_panel", "store_decoration"),
    ("详情页做3张", "five_panel", "detail"),
    ("改成五连图，左上角做logo", "three_panel", "five_panel"),
    ("副标题里写logo", "five_panel", "five_panel"),
])
def test_output_mentions_are_not_elements(text, fallback, expected):
    assert detect_output(text, fallback) == expected


def test_single_item_fullplan_preserves_entry_and_budget(client):
    _, asset, base = setup_creation(client)
    response = submit(client, base, asset, output_type="full_plan", delivery_types=["store_decoration"])
    assert response.status_code == 200, response.text
    result = confirm(client, base, response.json())
    assert result.status_code == 200, result.text
    task = client.get(f"/api/v1/tasks/{result.json()['task_id']}").json()
    assert task["result"]["entry_mode"] == "fullplan"
    assert task["result"]["output_type"] == "store_decoration"
    assert confirm(client, base, response.json()).json()["task_id"] == task["id"]
    with SessionLocal() as db:
        assert len(db.scalars(select(WorkflowTask)).all()) == 1
        assert not db.scalars(select(ModelCallRecord)).all()


def test_element_mention_does_not_change_intake_plan(client):
    _, asset, base = setup_creation(client)
    response = submit(client, base, asset, text="做五连图，左上角放logo；店名：测试店；主推：面食；不展示价格", output_type="five_panel")
    assert response.status_code == 200, response.text
    assert response.json()["snapshot"]["output_type"] == "five_panel"
    assert confirm(client, base, response.json()).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(DesignPlan)).plan["canvas"]["ratio"] == "20:3"


def test_negated_default_requires_clarification_before_understanding(client, monkeypatch):
    _, asset, base = setup_creation(client)
    monkeypatch.setattr("app.services.intake_understanding.understand", lambda *a: pytest.fail("Negated output must not invoke a model"))
    response = submit(client, base, asset, text="不要五图", output_type="five_panel", use_ai=True, accepted_understanding_policy="text-understanding-paid-v1")
    assert response.status_code == 409
    assert "OUTPUT_NEEDS_CLARIFICATION" in response.text


@pytest.mark.parametrize("output", ["five_panel", "three_panel", "logo", "store_decoration", "detail"])
def test_prompt_uses_same_regions_as_renderer(output):
    plan = build_design_plan({"store_name": "验收面馆"}, output_type=output)
    plan["render_mode"] = "illustration"
    prompt = build_visual_prompt(plan)
    for region in plan["layout"]["regions"]:
        if region["role"] in {"copy", "visual"}:
            x, y, w, h = region["box"]
            assert f"横向{x:.0%}—{x+w:.0%}、纵向{y:.0%}—{y+h:.0%}" in prompt
    assert "主体放在画面右侧" not in prompt
    assert "不出现任何文字" in prompt


def test_nonfood_prompt_not_forced_into_restaurant():
    plan = build_design_plan({"store_name": "验收美甲"}, "minimal", output_type="store_decoration")
    plan["render_mode"] = "illustration"
    assert "餐饮主题" not in build_visual_prompt(plan)
    plan["style"]["key"] = "appetite"
    assert "食物近景" not in build_visual_prompt(plan)


def test_failed_ocr_retains_exact_request_and_failed_audit(tmp_path, monkeypatch):
    plan = build_design_plan({"store_name": "验收面馆"})
    plan["render_mode"] = "illustration"
    save_generation_request(plan, tmp_path, "qwen")
    original = (tmp_path / "generation-request.json").read_bytes()
    def reject(*args):
        raise ValueError("底图含文字")
    monkeypatch.setattr("app.services.text_guard.check_background", reject)
    raw = io.BytesIO()
    Image.new("RGB", (2000, 300)).save(raw, "PNG")
    with pytest.raises(ValueError, match="底图含文字"):
        render_and_slice(raw.getvalue(), plan, tmp_path)
    assert (tmp_path / "model-visual.png").is_file()
    assert (tmp_path / "generation-request.json").read_bytes() == original
    audit = json.loads((tmp_path / "generation-audit.json").read_text())
    assert audit["status"] == "failed"
    assert audit["quality_checks"]["text_capacity"] == "not_checked"
    assert not (tmp_path / "long.png").exists()


def test_professional_draft_does_not_reuse_wrong_output_or_style(client):
    from test_generation_contract import seed
    from app.models import FactVersion, utc_now
    project, _, _ = seed()
    with SessionLocal() as db:
        db.add(FactVersion(project_id=project, version=1, confirmed_at=utc_now(), facts={"store_name": "验收面馆", "show_price": False}))
        db.commit()
    endpoint = f"/api/v1/projects/{project}/design-plans"
    first = client.post(endpoint, json={"output_type": "three_panel", "render_mode": "illustration", "style": "minimal"})
    assert first.status_code == 201, first.text
    again = client.post(endpoint, json={"output_type": "three_panel", "render_mode": "illustration", "style": "minimal"})
    assert again.json()["id"] == first.json()["id"]
    second = client.post(endpoint, json={"output_type": "logo", "style": "brand"})
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["plan"]["output_type"] == "logo"
    assert second.json()["plan"]["render_mode"] == "illustration"
    assert first.json()["plan"]["canvas"]["ratio"] == "12:3"


def test_professional_can_explicitly_omit_price(client):
    project = client.post("/api/v1/projects", json={"name": "验收店"}).json()["project_id"]
    response = client.post(f"/api/v1/projects/{project}/fact-versions", json={
        "store_name": "验收店", "positioning": "面食", "hero_item": "面食",
        "selling_points": ["聚餐"], "show_price": False})
    assert response.status_code == 200
    confirmed = client.post(f"/api/v1/projects/{project}/fact-versions/{response.json()['fact_version']}/confirm", json={"confirmed": True})
    assert confirmed.status_code == 200, confirmed.text


def test_model_style_hint_is_not_business_fact(client, monkeypatch):
    _, asset, base = setup_creation(client)
    monkeypatch.setattr("app.services.intake_understanding.understand", lambda *a: {
        "facts": {"store_name": "验收面馆", "positioning": "清爽简约"},
        "uncertain_fields": [], "style_hint": "minimal"})
    response = submit(client, base, asset, text="验收面馆，清爽简约", input_mode="chat", use_ai=True, accepted_understanding_policy="text-understanding-paid-v1")
    assert response.status_code == 200, response.text
    assert response.json()["snapshot"]["facts"].get("positioning") != "清爽简约"


def test_failed_result_does_not_offer_nonexistent_preview(client):
    from app.models import TaskStatus
    from app.services.dialogue_routing import route_reply
    project, _, _ = setup_creation(client)
    with SessionLocal() as db:
        task = WorkflowTask(project_id=project, task_type="group_buying_image_generation", status=TaskStatus.FAILED_FINAL)
        db.add(task); db.commit()
        response = route_reply(db, "文字重叠了，先检查，不要重新生成", task)
        assert not response["can_prepare"]
        assert response["model_calls"] == 0
        assert "没有可交付的预览" in response["next_steps"][0]


def test_request_is_saved_before_provider_and_failure_never_falls_back(client, monkeypatch):
    from test_generation_contract import seed, request
    from app.core.config import settings
    from app.models import StoreProject
    from app.services.image_generation import run_generation, ImageGenerationError
    project, plan_id, body = seed()
    response = client.post(f"/api/v1/projects/{project}/generation-runs", json=request(plan_id, body)).json()
    task_id = response["task_id"]
    calls = []
    def fail_provider(prompt, references):
        saved = json.loads((settings.generated_dir / project / task_id / "generation-request.json").read_text())
        assert saved["prompt"] == prompt
        assert saved["provider"] == "qwen"
        assert references == []
        calls.append(prompt)
        raise ImageGenerationError("TEST_PROVIDER_FAILURE", "模拟供应商故障")
    monkeypatch.setattr("app.services.image_generation.call_qwen", fail_provider)
    monkeypatch.setattr("app.services.image_generation.call_doubao", lambda *a: pytest.fail("Must not switch provider"))
    with SessionLocal() as db:
        run_generation(db, db.get(StoreProject, project), db.get(WorkflowTask, task_id), db.get(DesignPlan, plan_id), "qwen", True)
        records = db.scalars(select(ModelCallRecord).where(ModelCallRecord.task_id == task_id)).all()
        assert len(records) == len(calls) == 1
