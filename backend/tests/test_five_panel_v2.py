import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageChops, ImageDraw
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import DesignPlan, StoreProject, WorkflowTask, TaskStatus
from app.services.design_plan import build_design_plan, validate_design_plan
from app.services.image_generation import build_visual_prompt, render_and_slice, _font
from app.services.intake import parse_text
from app.services.master_layout import compose_master
from test_m1_creations import setup_creation, submit, confirm


@pytest.mark.parametrize("text", ["山西面馆五图", "山西面馆", "给山西面馆做一套五连图"])
def test_short_request_is_not_another_form(text):
    assert parse_text(text)["store_name"] == "山西面馆"


def test_brand_only_has_registered_whole_canvas_layout():
    plan = build_design_plan({"store_name": "山西面馆", "show_price": False})
    plan["render_mode"] = "illustration"
    validate_design_plan(plan)
    assert plan["creative_direction"]["category"] == "面食"
    assert not plan["locked_facts"]["hero_item"]
    assert plan["copy"]["price"] == ""
    assert all(not f["headline"] for f in plan["frames"])
    assert plan["layout"]["id"].startswith("L")
    prompt = build_visual_prompt(plan)
    assert "面食" in prompt
    assert "仅提供了店名：制作抽象" not in prompt
    assert "左右各五分之一留白" not in prompt
    assert "山西面馆" not in prompt  # Business text belongs only to the typography layer.


def test_hidden_brand_and_price_are_not_reintroduced():
    plan = build_design_plan({"store_name": "山西面馆", "hero_price": "99元",
                              "show_price": False, "show_store_name": False})
    assert all("山西面馆" not in f["headline"] + f["support"] for f in plan["frames"])
    assert "99元" not in json.dumps(plan, ensure_ascii=False)


def test_unknown_brand_uses_still_life_not_fake_menu():
    plan = build_design_plan({"store_name": "测试品牌"})
    assert plan["creative_direction"]["category"] == "品牌主题"
    assert "餐具" in plan["creative_direction"]["visuals"][0] or "餐碗" in plan["creative_direction"]["visuals"][0]
    assert not plan["locked_facts"]["hero_item"]


def test_copy_reaches_template_region_and_exact_slices(tmp_path):
    plan = build_design_plan({"store_name": "山西面馆"})
    plan["render_mode"] = "illustration"
    # Synthetic model output verifies composition, not model aesthetic quality.
    background = Image.new("RGB", (2000, 300), "#ce8b42")
    draw = ImageDraw.Draw(background)
    for i in range(5):
        draw.ellipse((i*400+110, 45, i*400+320, 180), fill="#eee4ce")
    raw = io.BytesIO()
    background.save(raw, "PNG")
    result = render_and_slice(raw.getvalue(), plan, tmp_path)
    no_text = json.loads(json.dumps(plan))
    no_text["copy"] = {}
    comparison = compose_master(background, no_text, [], _font)
    with Image.open(tmp_path / "long-clean.png") as clean:
        assert ImageChops.difference(clean, comparison).getbbox()
    with Image.open(tmp_path / "long.png") as master:
        for i, file in enumerate(result["slices"]):
            with Image.open(tmp_path / file) as part:
                assert ImageChops.difference(master.crop((i*800,0,(i+1)*800,600)),part).getbbox() is None
    audit = json.loads((tmp_path / "generation-audit.json").read_text())
    assert audit["contract"] == "region-master-v3"
    assert audit["quality_checks"]["semantic_visual_review"] == "not_automated"


def test_empty_plan_is_rejected_before_model(client, monkeypatch):
    from app.services import image_generation
    pid, _, _ = setup_creation(client)
    with SessionLocal() as db:
        project = db.get(StoreProject, pid)
        task = WorkflowTask(project_id=pid, task_type="group_buying_image_generation")
        db.add(task); db.commit()
        plan = build_design_plan({"store_name": "山西面馆"})
        plan["render_mode"] = "illustration"
        plan["copy"] = {}
        monkeypatch.setattr(image_generation, "call_qwen", lambda *a: pytest.fail("Invalid plan must not charge"))
        image_generation.run_generation(db, project, task, SimpleNamespace(plan=plan), "qwen", False)
        assert task.status == TaskStatus.FAILED_FINAL
        assert task.error_code == "MASTER_PREFLIGHT_FAILED"


def test_actual_user_request_to_worker_mock(client, monkeypatch):
    from app.services import image_generation
    _, asset, base = setup_creation(client)
    review = submit(client, base, asset, asset_ids=[], text="山西面馆五图",
                    input_mode="chat", allow_illustration=True).json()
    assert review["snapshot"]["ready"]
    assert not review["snapshot"]["gaps"]
    response = confirm(client, base, review)
    assert response.status_code == 200
    calls = []
    def fake_model(prompt, references):
        calls.append(prompt)
        assert "面食" in prompt
        assert references == []
        raw = io.BytesIO(); Image.new("RGB", (2000,300), "#ce8b42").save(raw,"PNG")
        return raw.getvalue()
    monkeypatch.setattr(image_generation, "call_qwen", fake_model)
    with SessionLocal() as db:
        task = db.get(WorkflowTask, response.json()["task_id"])
        plan = db.scalar(select(DesignPlan).where(DesignPlan.project_id == task.project_id))
        image_generation.run_generation(db, db.get(StoreProject, task.project_id), task, plan, "qwen", False)
        assert task.status == TaskStatus.SUCCEEDED
        assert len(calls) == 1
        assert len(task.result["slices"]) == 5
        assert plan.plan["template_version"] == "region-master-v3"
