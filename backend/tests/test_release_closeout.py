"""Offline regressions for continuation, format, billing and post-processing boundaries."""
import io
import pytest
from PIL import Image
from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import CreationConfirmation, DesignPlan, WorkflowTask, StoreProject, TaskStatus, ModelCallRecord, ModelUsageRecord
from app.services import image_generation as generation
from test_m1_creations import setup_creation, submit, confirm


def test_three_panel_reaches_confirmation_and_exports(client, tmp_path):
    project, asset, base = setup_creation(client)
    snap = submit(client, base, asset, text="店名：测试面馆，主推：牛肉面，做三连图", input_mode="chat").json()
    assert snap["snapshot"]["output_type"] == "three_panel"
    assert "五图" not in snap["snapshot"]["messages"][-1]["content"]
    response = confirm(client, base, snap)
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        record = db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id == response.json()["task_id"]))
        plan = db.get(DesignPlan, record.plan_id).plan
        plan["render_mode"] = "illustration"
        buffer = io.BytesIO(); Image.new("RGB", (1200, 300), "#444444").save(buffer, format="PNG")
        result = generation.render_and_slice(buffer.getvalue(), plan, tmp_path)
        assert (result["width"], result["height"]) == (2400, 600)
        assert len(result["slices"]) == 3
        for name in result["slices"]:
            with Image.open(tmp_path/name) as image:
                assert image.size == (800, 600)


def test_model_success_local_failure_never_calls_second_provider(client, monkeypatch, tmp_path):
    project, asset, base = setup_creation(client)
    snap = submit(client, base, asset).json()
    task_id = confirm(client, base, snap).json()["task_id"]
    monkeypatch.setattr(settings, "generated_dir", tmp_path)
    monkeypatch.setattr(generation, "call_qwen", lambda *args: b"invalid-image")
    monkeypatch.setattr(generation, "call_doubao", lambda *args: pytest.fail("local failure must not incur a second image call"))
    with SessionLocal() as db:
        task = db.get(WorkflowTask, task_id)
        confirmation = db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id == task_id))
        generation.run_generation(db, db.get(StoreProject, project), task, db.get(DesignPlan, confirmation.plan_id), "qwen", True)
        assert task.status == TaskStatus.FAILED_FINAL
        assert task.error_code == "POSTPROCESS_FAILED"
        call = db.scalar(select(ModelCallRecord).where(ModelCallRecord.task_id == task_id))
        assert call.status == "SUCCEEDED"
    assert generation.REQUEST_CONTEXT.get() is None
    assert generation.CALL_METRICS.get() is None


def test_qwen_parameters_and_actual_usage(monkeypatch):
    monkeypatch.setattr(settings, "dashscope_api_key", "test-not-a-key")
    seen = []
    class Response:
        status_code = 200
        content = b"test-bytes"
        def json(self):
            return {"usage": {"image_count": 1}, "output": {"choices": [{"message": {"content": [{"image": "https://example.invalid/image"}]}}]}}
        def raise_for_status(self): pass
    def post(*args, **kwargs):
        seen.append(kwargs["json"])
        return Response()
    monkeypatch.setattr(generation.httpx, "post", post)
    monkeypatch.setattr(generation.httpx, "get", lambda *args, **kwargs: Response())
    token = generation.REQUEST_CONTEXT.set({"size": "1200*300"})
    metrics = generation.CALL_METRICS.set(None)
    try:
        assert generation.call_qwen("无字底图", []) == b"test-bytes"
        assert seen[0]["parameters"]["size"] == "1200*300"
        assert seen[0]["parameters"]["n"] == 1
        assert generation.CALL_METRICS.get()["usage"] == {"image_count": 1}
        assert generation.CALL_METRICS.get()["download_ms"] >= 1
    finally:
        generation.REQUEST_CONTEXT.reset(token)
        generation.CALL_METRICS.reset(metrics)


def test_usage_report_does_not_expose_prompts_or_invent_tokens(client):
    project, _, _ = setup_creation(client)
    with SessionLocal() as db:
        task = WorkflowTask(project_id=project, task_type="test", status=TaskStatus.SUCCEEDED)
        db.add(task); db.flush()
        call = ModelCallRecord(project_id=project, task_id=task.id, provider="qwen", model="test", contract="test", status="SUCCEEDED")
        db.add(call); db.flush()
        db.add(ModelUsageRecord(call_id=call.id, usage={"image_count": 1}, request_ms=100, download_ms=20, prompt_characters=200, prompt_sha256="a"*64, request_options={}))
        db.commit()
    response = client.get(f"/api/v1/projects/{project}/usage")
    assert response.status_code == 200
    item = response.json()["calls"][0]
    assert item["input_tokens"] is None
    assert item["image_usage"] == {"image_count": 1}
    assert "prompt" not in item and "request_options" not in item


@pytest.mark.parametrize("direction", ["logo", "package_main", "voucher_main", "dish", "promotion", "store_decoration", "detail"])
def test_single_output_safe_area_and_export(client, direction, tmp_path):
    from app.services.design_plan import build_design_plan, validate_design_plan
    plan = build_design_plan({"store_name":"测试店", "hero_item":"好好享受这一刻"}, output_type=direction)
    plan["render_mode"] = "illustration"
    validate_design_plan(plan)
    assert generation.request_size(plan) == "1024*768"
    if direction in {"logo", "package_main", "voucher_main"}:
        for region in plan["layout"]["regions"]:
            x, y, w, h = region["box"]
            assert x >= .125 and x+w <= .875 and y >= 0 and y+h <= 1
    buffer = io.BytesIO(); Image.new("RGB", (1024,768), "#333333").save(buffer,format="PNG")
    result = generation.render_and_slice(buffer.getvalue(), plan, tmp_path)
    assert len(result["slices"]) == 1
    assert (result["width"],result["height"]) == (800,600)


def test_full_plan_budget_and_preserved_outputs(client, monkeypatch, tmp_path):
    project, asset, base = setup_creation(client)
    snap = submit(client,base,asset,output_type="full_plan").json()
    denied = confirm(client,base,snap)
    assert denied.status_code == 409 and "BATCH_BUDGET_REQUIRED" in denied.text
    approved = confirm(client,base,snap,approved_image_calls=3)
    assert approved.status_code == 200,approved.text
    monkeypatch.setattr(settings,"generated_dir",tmp_path)
    calls=[]
    def image_call(prompt,refs):
        calls.append(prompt)
        buffer=io.BytesIO();Image.new("RGB",(1024,768),"#333333").save(buffer,format="PNG")
        return buffer.getvalue()
    monkeypatch.setattr(generation,"call_qwen",image_call)
    with SessionLocal() as db:
        task=db.get(WorkflowTask,approved.json()["task_id"])
        record=db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id==task.id))
        generation.run_generation(db,db.get(StoreProject,project),task,db.get(DesignPlan,record.plan_id),"qwen",False)
        assert task.status == TaskStatus.SUCCEEDED,task.error_message
        assert len(calls)==3
        generation.run_generation(db,db.get(StoreProject,project),task,db.get(DesignPlan,record.plan_id),"qwen",False)
        assert len(calls)==3, "a completed task must never repeat paid calls"
        deliveries=task.result["deliverables"]
        assert [d["output_type"] for d in deliveries] == ["voucher_main","five_panel","logo"]
        assert [len(d["slices"]) for d in deliveries] == [1,5,1]
        child_id=deliveries[0]["task_id"]
    assert client.get(f"/api/v1/projects/{project}/generations/{child_id}/assets/long.png").status_code==200
    assert confirm(client,base,snap,approved_image_calls=3).json()["task_id"] == approved.json()["task_id"]
    assert len(calls)==3


def test_multi_detail_requests_explicit_budget(client):
    _,asset,base=setup_creation(client)
    snap=submit(client,base,asset,text="店名：测试店，主推：牛肉面，做3张详情页",input_mode="chat").json()
    assert snap["snapshot"]["delivery_types"] == ["detail"]*3
    assert confirm(client,base,snap).status_code == 409
    assert confirm(client,base,snap,approved_image_calls=3).status_code == 200


def test_batch_failure_preserves_completed_and_stops_remaining(client, monkeypatch, tmp_path):
    project,asset,base=setup_creation(client)
    snap=submit(client,base,asset,output_type="full_plan").json()
    task_id=confirm(client,base,snap,approved_image_calls=3).json()["task_id"]
    monkeypatch.setattr(settings,"generated_dir",tmp_path)
    calls=[]
    def response(*args):
        calls.append(1)
        if len(calls)==2: return b"invalid-image"
        buffer=io.BytesIO(); Image.new("RGB",(1024,768),"#333333").save(buffer,format="PNG")
        return buffer.getvalue()
    monkeypatch.setattr(generation,"call_qwen",response)
    with SessionLocal() as db:
        task=db.get(WorkflowTask,task_id)
        record=db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id==task_id))
        generation.run_generation(db,db.get(StoreProject,project),task,db.get(DesignPlan,record.plan_id),"qwen",False)
        assert task.error_code == "BATCH_PART_FAILED"
        assert len(calls)==2
        assert task.result["deliverables"][0]["status"]=="SUCCEEDED"
        assert task.result["deliverables"][0]["long_image"]=="long.png"
        generation.run_generation(db,db.get(StoreProject,project),task,db.get(DesignPlan,record.plan_id),"qwen",False)
        assert len(calls)==2


def test_batch_pause_during_provider_call_never_starts_next_item(client, monkeypatch, tmp_path):
    project,asset,base=setup_creation(client)
    snap=submit(client,base,asset,output_type="full_plan").json()
    task_id=confirm(client,base,snap,approved_image_calls=3).json()["task_id"]
    monkeypatch.setattr(settings,"generated_dir",tmp_path)
    calls=[]
    def response(*args):
        calls.append(1)
        assert client.post(f"/api/v1/tasks/{task_id}/pause").status_code==200
        buffer=io.BytesIO(); Image.new("RGB",(1024,768),"#333333").save(buffer,format="PNG")
        return buffer.getvalue()
    monkeypatch.setattr(generation,"call_qwen",response)
    with SessionLocal() as db:
        task=db.get(WorkflowTask,task_id)
        record=db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id==task_id))
        generation.run_generation(db,db.get(StoreProject,project),task,db.get(DesignPlan,record.plan_id),"qwen",False)
        assert task.status == TaskStatus.NEEDS_USER
        assert len(calls)==1
        assert len(task.result["deliverables"])==1
