import io
import json
from copy import deepcopy
import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import CreationConfirmation, DesignPlan, WorkflowTask, StoreProject, TaskStatus, ModelCallRecord
from app.services.creative_workflow import reserve_context, compact_layout, copy_draft_valid, parse_copy_edit
from app.services.layout_catalog import ALL_LAYOUTS, select_layout
from app.services.design_plan import build_design_plan, validate_design_plan
from app.services.image_generation import run_generation, _font
from app.services.master_layout import fitted_text
from app.services.category_policy import resolve_category
from test_m1_creations import setup_creation, submit, confirm


def test_eighteen_templates_single_asset_rotation():
    assert len(ALL_LAYOUTS) == 18
    last = []
    for i in range(50):
        layout = select_layout({"store_name":"相同店名"}, asset_count=1, excluded_ids=last[-5:], selection_key=str(i))
        assert layout["id"] not in last[-5:]
        assert len([r for r in layout["regions"] if r["role"] == "visual"]) == 1
        last.append(layout["id"])
    with pytest.raises(ValueError):
        select_layout({}, excluded_ids=[v["id"] for v in ALL_LAYOUTS])


def test_project_history_used_and_other_project_isolated(client):
    project,asset,base = setup_creation(client)
    seen = []
    for i in range(8):
        if i:
            c = client.post(f"/api/v1/projects/{project}/creations",json={}).json()
            base = f"/api/v1/projects/{project}/creations/{c['creation_id']}"
        snap = submit(client,base,asset).json()
        response = confirm(client,base,snap)
        assert response.status_code == 200, response.text
        with SessionLocal() as db:
            record = db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id == response.json()["task_id"]))
            plan = db.get(DesignPlan,record.plan_id).plan
            key = plan["layout"]["id"]
            assert key not in seen[-5:]
            seen.append(key)
        assert confirm(client,base,snap).json()["task_id"] == response.json()["task_id"]
    other,_,_ = setup_creation(client)
    with SessionLocal() as db:
        assert reserve_context(db,other) == []
        db.rollback()


def test_review_sources_never_enter_runtime_and_size_tamper_fails():
    plan = build_design_plan({"store_name":"测试面馆"})
    plan["layout"]["reference_image"] = "/secret/case.png"
    plan["layout"]["review_notes"] = "第三方品牌与独特文案"
    payload = json.dumps(compact_layout(plan["layout"]),ensure_ascii=False)
    assert "secret" not in payload and "第三方" not in payload
    plan["canvas"]["recommended_size"] = "5000x600"
    with pytest.raises(ValueError,match="规格"):
        validate_design_plan(plan)


@pytest.mark.parametrize("name,primary",[("美甲店","beauty"),("桌游馆","leisure"),("鲜花店","shopping"),("面馆","food"),("未知品牌","general")])
def test_category_routes_without_forcing_food(name,primary):
    plan = build_design_plan({"store_name":name})
    assert plan["category"]["primary"] == primary
    if primary not in {"food"}:
        assert "餐碗" not in plan["creative_direction"]["subject"]


def test_creative_draft_safety_and_explicit_copy():
    assert copy_draft_valid({"headline":"把这一餐，留给好心情"}, {})
    for title in ("全国第一面馆","手工现包，限时9元","永久逆龄，保证有效"):
        assert not copy_draft_valid({"headline":title},{})
    assert parse_copy_edit("只把标题改成：今晚一起吃面") == "今晚一起吃面"
    assert parse_copy_edit("标题改成晚餐，再换一种配色") is None


def test_long_unbroken_text_never_overflows_width():
    im=Image.new("RGB",(400,150));draw=ImageDraw.Draw(im)
    with pytest.raises(ValueError):
        fitted_text(draw,"W",(0,0,1,100),_font,"white")


def test_explicit_title_edit_no_understanding_or_image_calls(client,monkeypatch,tmp_path):
    from app.services import intake_understanding, image_generation
    project,asset,base = setup_creation(client)
    original = submit(client,base,asset,input_mode="chat").json()
    task_id = confirm(client,base,original).json()["task_id"]
    with SessionLocal() as db:
        task=db.get(WorkflowTask,task_id);task.status=TaskStatus.SUCCEEDED;db.commit()
    monkeypatch.setattr(settings,"generated_dir",tmp_path)
    source=tmp_path/project/task_id;source.mkdir(parents=True)
    Image.new("RGB",(2000,300),"#552222").save(source/"model-visual.png")
    child=client.post(f"/api/v1/projects/{project}/creations",json={"parent_creation_id":original["creation_id"]}).json()
    child_base=f"/api/v1/projects/{project}/creations/{child['creation_id']}"
    monkeypatch.setattr(intake_understanding,"_post_chat",lambda *a:pytest.fail("No understanding charge"))
    edited=submit(client,child_base,asset,text="标题改成今晚一起吃面",input_mode="chat",use_ai=True,accepted_understanding_policy="text-understanding-paid-v1").json()
    assert edited["snapshot"]["copy_edit"] == "今晚一起吃面"
    result=confirm(client,child_base,edited)
    assert result.status_code == 200,result.text
    monkeypatch.setattr(image_generation,"call_qwen",lambda *a:pytest.fail("No image charge"))
    with SessionLocal() as db:
        task=db.get(WorkflowTask,result.json()["task_id"])
        record=db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id==task.id))
        plan=db.get(DesignPlan,record.plan_id)
        original_bytes=(source/"model-visual.png").read_bytes()
        run_generation(db,db.get(StoreProject,project),task,plan,"qwen",False)
        assert task.status == TaskStatus.SUCCEEDED,task.error_message
        assert task.result["image_model_calls"] == 0
        assert (source/"model-visual.png").read_bytes() == original_bytes
        assert db.scalar(select(ModelCallRecord).where(ModelCallRecord.task_id==task.id)) is None
