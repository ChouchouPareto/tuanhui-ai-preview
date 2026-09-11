import io
from datetime import timedelta

from PIL import Image
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import CreationConfirmation, DesignPlan, FactVersion, IntakeRevision, TaskStatus, WorkflowTask, utc_now


def setup_creation(client, dish=True):
    project = client.post("/api/v1/projects", json={"name": "测试店"}).json()["project_id"]
    data = io.BytesIO()
    Image.new("RGB", (400, 300), "green").save(data, "PNG")
    asset = client.post(f"/api/v1/projects/{project}/assets", data={"asset_type": "product" if dish else "storefront", "semantic_role": "dish" if dish else "storefront"}, files={"file": ("dish.png", data.getvalue(), "image/png")}).json()["asset_id"]
    base = f"/api/v1/projects/{project}/creations"
    creation = client.post(base, json={}).json()["creation_id"]
    return project, asset, f"{base}/{creation}"


def submit(client, base, asset, **kwargs):
    body = {"expected_revision": 0, "text": "店名：测试店；主推：清蒸鱼；不展示价格", "asset_ids": [asset], **kwargs}
    return client.post(f"{base}/intake-runs", json=body, headers={"Idempotency-Key": f"input-{body['expected_revision']}"})


def confirm(client, base, review, **kwargs):
    return client.post(f"{base}/confirm", headers={"Idempotency-Key": "confirm-1"}, json={"expected_revision": review["revision"], "snapshot_hash": review["snapshot_hash"], "accepted_budget_policy": "local-paid-generation-v1", "materials_confirmed": True, **kwargs})


def test_complete_intake_without_storefront_price_or_model(client):
    project, asset, base = setup_creation(client)
    response = submit(client, base, asset)
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["snapshot"]["ready"]
    assert review["snapshot"]["show_price"] is False
    assert review["snapshot"]["facts"]["hero_price"] == ""
    first = confirm(client, base, review)
    assert first.status_code == 200, first.text
    assert confirm(client, base, review).json()["task_id"] == first.json()["task_id"]
    with SessionLocal() as db:
        assert len(db.scalars(select(WorkflowTask)).all()) == 1
        plan = db.scalar(select(DesignPlan))
        assert plan.plan["copy"]["price"] == ""
        assert plan.plan["selected_asset_ids"] == [asset]
        assert not db.scalars(select(FactVersion)).all()  # No project-memory overwrite.
    assert client.get(base + "/review").json()["task_id"] == first.json()["task_id"]
    assert submit(client, base, asset, expected_revision=1).status_code == 409


def test_missing_dish_and_no_ai_authorization(client):
    _, asset, base = setup_creation(client, dish=False)
    review = submit(client, base, asset).json()
    assert review["snapshot"]["gaps"][0]["field"] == "assets"
    assert confirm(client, base, review).status_code == 409
    assert submit(client, base, asset, expected_revision=1, use_ai=True).status_code == 409


def test_input_revision_and_idempotency(client):
    _, asset, base = setup_creation(client)
    first = submit(client, base, asset).json()
    assert submit(client, base, asset).json()["revision"] == 1
    assert submit(client, base, asset, text="不同内容").status_code == 409
    second = submit(client, base, asset, expected_revision=1, answers={"hero_item": "蒸鱼"}).json()
    assert second["revision"] == 2
    assert confirm(client, base, first).status_code == 409
    with SessionLocal() as db:
        assert len(db.scalars(select(IntakeRevision)).all()) == 2


def test_conditional_questions_and_asset_scope(client):
    _, asset, base = setup_creation(client)
    _, other, _ = setup_creation(client)
    assert submit(client, base, other).status_code == 404
    review = submit(client, base, asset, text="做五图", show_store_name=False, show_price=True).json()
    assert {g["field"] for g in review["snapshot"]["gaps"]} == {"hero_price"}
    review = submit(client, base, asset, expected_revision=1, text="做五图", show_store_name=False, show_price=False, answers={"hero_item": "清蒸鱼"}).json()
    assert review["snapshot"]["ready"]
    assert confirm(client, base, review, materials_confirmed=False).status_code == 409
    assert confirm(client, base, review, accepted_budget_policy="free").status_code == 422


def test_asset_changed_after_review_rejected(client):
    project, asset, base = setup_creation(client)
    review = submit(client, base, asset).json()
    client.patch(f"/api/v1/projects/{project}/assets/{asset}", json={"semantic_role": "menu"})
    assert confirm(client, base, review).status_code == 409


def test_worker_executes_confirmed_task_once(client, monkeypatch):
    from app import worker
    _, asset, base = setup_creation(client)
    review = submit(client, base, asset).json()
    confirm(client, base, review)
    calls = []
    def generate(db, project, task, plan, provider, fallback):
        calls.append(task.id)
        assert fallback is False
        task.status = TaskStatus.SUCCEEDED
        task.progress = 100
        db.commit()
    monkeypatch.setattr(worker, "run_generation", generate)
    assert worker.run_once()
    assert worker.run_once() is False
    assert len(calls) == 1


def test_expired_claim_never_repeats_paid_call(client, monkeypatch):
    from app import worker
    _, asset, base = setup_creation(client)
    confirm(client, base, submit(client, base, asset).json())
    with SessionLocal() as db:
        record = db.scalar(select(CreationConfirmation))
        record.state = "RUNNING"
        record.lease_until = utc_now() - timedelta(minutes=1)
        db.commit()
    monkeypatch.setattr(worker, "run_generation", lambda *a: (_ for _ in ()).throw(AssertionError("must not retry")))
    worker.run_once()
    with SessionLocal() as db:
        assert db.scalar(select(CreationConfirmation)).state == "RECONCILING"
        assert db.scalar(select(WorkflowTask)).error_code == "RECONCILING"


def test_confirmed_project_memory_is_reused_without_overwrite(client):
    project, asset, base = setup_creation(client)
    with SessionLocal() as db:
        db.add(FactVersion(project_id=project, version=1, facts={"store_name": "记忆店名", "hero_item": "蒸鱼"}, evidence={}, confirmed_at=utc_now()))
        db.commit()
    review = submit(client, base, asset, text="做五图，不展示价格").json()
    assert review["snapshot"]["ready"]
    assert review["snapshot"]["facts"]["store_name"] == "记忆店名"
    assert review["snapshot"]["sources"]["store_name"] == "project_confirmed"
