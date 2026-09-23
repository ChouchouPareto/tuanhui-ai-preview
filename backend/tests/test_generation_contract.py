"""Offline professional plan binding, deduplication and paid-call boundary regressions."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event

import httpx
import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import DesignPlan, FactVersion, ModelCallRecord, ProfessionalGenerationJob, StoreProject, TaskStatus, WorkflowTask, utc_now
from app.services.design_plan import build_design_plan
from app.services.generation_contract import plan_digest
from app.services import image_generation as generation


def seed(version=1, project_id=None, status="CONFIRMED"):
    with SessionLocal() as db:
        project = db.get(StoreProject, project_id) if project_id else StoreProject(name="山西面馆", current_fact_version=1)
        if not project_id:
            db.add(project)
            db.flush()
        body = build_design_plan({"store_name": "山西面馆"}, selection_key=str(version))
        body["render_mode"] = "illustration"
        plan = DesignPlan(project_id=project.id, fact_version=1, version=version,
                          status=status, confirmed_at=utc_now() if status == "CONFIRMED" else None, plan=body)
        db.add(plan)
        db.commit()
        return project.id, plan.id, deepcopy(body)


def request(plan_id, body, **kwargs):
    return {"plan_id": plan_id, "plan_hash": plan_digest(body), **kwargs}


@pytest.fixture
def executor(monkeypatch):
    # R6 reservations live in the DB; the API must never start execution itself.
    monkeypatch.setattr("app.api.execute_generation", lambda *args: pytest.fail("API executed an in-process model job"))
    class QueueProbe:
        def items(self):
            with SessionLocal() as db:
                return [(j.project_id, j.task_id, j.plan_id, j.snapshot["contract"]["provider"], False)
                        for j in db.scalars(select(ProfessionalGenerationJob).order_by(ProfessionalGenerationJob.created_at)).all()]
        def __len__(self):
            return len(self.items())
        def __eq__(self, other):
            return self.items() == other
    return QueueProbe()


def submit(client, project, payload):
    return client.post(f"/api/v1/projects/{project}/generation-runs", json=payload)


def test_reviewed_plan_is_not_reselected_or_replaced(client, executor, monkeypatch):
    project, plan_id, body = seed()
    def forbidden(*args, **kwargs):
        pytest.fail("Execution must not select a different layout")
    monkeypatch.setattr("app.services.layout_catalog.select_layout", forbidden)
    result = submit(client, project, request(plan_id, body, allow_fallback=True))
    assert result.status_code == 202
    assert result.json()["plan_hash"] == plan_digest(body)
    assert result.json()["allow_fallback"] is False
    assert executor == [(project, result.json()["task_id"], plan_id, "qwen", False)]
    with SessionLocal() as db:
        assert len(db.scalars(select(DesignPlan)).all()) == 1
        assert db.get(DesignPlan, plan_id).plan == body


def test_explicit_old_plan_not_latest_is_used(client, executor):
    project, plan_id, body = seed()
    seed(2, project)
    response = submit(client, project, request(plan_id, body))
    assert response.status_code == 202
    assert response.json()["plan_id"] == plan_id
    assert response.json()["binding_mode"] == "explicit"
    read = client.get(f"/api/v1/projects/{project}/design-plans/{plan_id}")
    assert read.json()["plan_hash"] == plan_digest(body)


def test_new_layout_is_selected_before_review_not_at_execution(client, executor):
    project, old_id, old_body = seed()
    with SessionLocal() as db:
        db.add(FactVersion(project_id=project, version=1, confirmed_at=utc_now(), facts={"store_name": "山西面馆"}))
        db.commit()
    created = client.post(f"/api/v1/projects/{project}/design-plans", json={"style": "brand"})
    assert created.status_code == 201
    new = created.json()
    assert new["plan"]["layout"]["id"] != old_body["layout"]["id"]
    confirmed = client.post(f"/api/v1/projects/{project}/design-plans/{new['id']}/confirm",
                            json={"confirmed": True, "plan_hash": new["plan_hash"]})
    assert confirmed.status_code == 200
    result = submit(client, project, request(new["id"], new["plan"]))
    assert result.status_code == 202
    assert result.json()["plan_hash"] == new["plan_hash"]
    assert client.get(f"/api/v1/projects/{project}/design-plans/{new['id']}").json()["plan"] == new["plan"]


def test_foreign_plan_cannot_be_read(client):
    project, _, _ = seed()
    _, foreign, _ = seed()
    assert client.get(f"/api/v1/projects/{project}/design-plans/{foreign}").status_code == 404


def test_invalid_geometry_cannot_be_confirmed(client):
    project, plan_id, body = seed(status="DRAFT")
    with SessionLocal() as db:
        body["canvas"]["ratio"] = "1:1"
        db.get(DesignPlan, plan_id).plan = body
        db.commit()
    response = client.post(f"/api/v1/projects/{project}/design-plans/{plan_id}/confirm", json={"confirmed": True})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_DESIGN_PLAN"


def test_legacy_request_freezes_resolved_plan_and_replays(client, executor):
    project, plan_id, body = seed()
    first = submit(client, project, {})
    second = submit(client, project, {})
    assert first.status_code == second.status_code == 202
    assert first.json()["plan_id"] == plan_id
    assert first.json()["binding_mode"] == "legacy_latest"
    assert second.json()["replayed"] is True
    assert first.json()["task_id"] == second.json()["task_id"]
    assert len(executor) == 1


@pytest.mark.parametrize("state", [TaskStatus.SUCCEEDED, TaskStatus.FAILED_FINAL, TaskStatus.NEEDS_USER])
def test_terminal_task_replay_never_regenerates(client, executor, state):
    project, plan_id, body = seed()
    first = submit(client, project, request(plan_id, body)).json()
    with SessionLocal() as db:
        db.get(WorkflowTask, first["task_id"]).status = state
        db.commit()
    replay = submit(client, project, request(plan_id, body)).json()
    assert replay["task_id"] == first["task_id"]
    assert replay["status"] == state.value
    assert replay["replayed"] is True and len(executor) == 1


def test_new_request_after_completion_is_distinct_but_preserves_layout(client, executor):
    project, plan_id, body = seed()
    first = submit(client, project, request(plan_id, body)).json()
    with SessionLocal() as db:
        db.get(WorkflowTask, first["task_id"]).status = TaskStatus.SUCCEEDED
        db.commit()
    second = submit(client, project, request(plan_id, body, request_id="explicit-new-attempt")).json()
    assert second["task_id"] != first["task_id"]
    assert second["plan_hash"] == first["plan_hash"]
    assert len(executor) == 2


def test_request_key_cannot_change_provider(client, executor):
    project, plan_id, body = seed()
    submit(client, project, request(plan_id, body, request_id="one-click"))
    response = submit(client, project, request(plan_id, body, request_id="one-click", provider="doubao"))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REQUEST_CONFLICT"
    assert len(executor) == 1


def test_other_active_task_is_not_returned_as_this_plan(client, executor):
    project, plan_id, body = seed()
    submit(client, project, request(plan_id, body))
    _, other_id, other_body = seed(2, project)
    response = submit(client, project, request(other_id, other_body))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "GENERATION_IN_PROGRESS"
    assert len(executor) == 1


@pytest.mark.parametrize("case,expected", [("hash", "PLAN_CHANGED"), ("facts", "FACT_VERSION_CHANGED"), ("draft", "PLAN_NOT_CONFIRMED"), ("foreign", "PLAN_NOT_FOUND")])
def test_invalid_binding_never_schedules(client, executor, case, expected):
    project, plan_id, body = seed(status="DRAFT" if case == "draft" else "CONFIRMED")
    payload = request(plan_id, body)
    if case == "hash":
        payload["plan_hash"] = "0" * 64
    elif case == "facts":
        with SessionLocal() as db:
            db.get(StoreProject, project).current_fact_version = 2
            db.commit()
    elif case == "foreign":
        _, other, other_body = seed()
        payload = request(other, other_body)
    response = submit(client, project, payload)
    assert response.status_code in (404, 409)
    assert response.json()["detail"]["code"] == expected
    assert executor == []
    with SessionLocal() as db:
        assert db.scalars(select(WorkflowTask)).all() == []


def test_hash_pair_is_required(client, executor):
    project, plan_id, body = seed()
    assert submit(client, project, {"plan_id": plan_id}).status_code == 422
    assert submit(client, project, {"plan_hash": plan_digest(body)}).status_code == 422
    assert not executor


def test_stale_confirmation_rejected_and_preview_exposes_hash(client):
    project, plan_id, body = seed(status="DRAFT")
    preview = client.get(f"/api/v1/projects/{project}/design-plans/latest").json()
    assert preview["plan_hash"] == plan_digest(body)
    assert client.patch(f"/api/v1/projects/{project}/design-plans/{plan_id}", json={"headline": "一碗热面"}).status_code == 200
    response = client.post(f"/api/v1/projects/{project}/design-plans/{plan_id}/confirm",
                           json={"confirmed": True, "plan_hash": preview["plan_hash"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PLAN_CHANGED"
    with SessionLocal() as db:
        assert db.get(DesignPlan, plan_id).status == "DRAFT"


def test_concurrent_duplicate_submissions_schedule_once(client, executor):
    project, plan_id, body = seed()
    barrier = Barrier(2)
    def send():
        barrier.wait(timeout=5)
        return submit(client, project, request(plan_id, body, request_id="double-click"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send(), range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    assert len({r.json()["task_id"] for r in responses}) == 1
    assert len(executor) == 1


def test_execution_rechecks_content_before_any_model_call(client, executor, monkeypatch):
    project, plan_id, body = seed()
    result = submit(client, project, request(plan_id, body)).json()
    monkeypatch.setattr(generation, "_run_generation", lambda *a: pytest.fail("Changed plan executed"))
    with SessionLocal() as db:
        plan = db.get(DesignPlan, plan_id)
        changed = deepcopy(plan.plan)
        changed["copy"]["headline"] = "未经确认的新标题"
        plan.plan = changed
        db.commit()
        task = db.get(WorkflowTask, result["task_id"])
        generation.run_generation(db, db.get(StoreProject, project), task, plan, "qwen", False)
        assert task.status == TaskStatus.NEEDS_USER
        assert task.error_code == "EXECUTION_CONTRACT_CHANGED"
        assert db.scalars(select(ModelCallRecord)).all() == []


def test_provider_failure_never_switches_and_replay_keeps_contract(client, executor, monkeypatch):
    project, plan_id, body = seed()
    result = submit(client, project, request(plan_id, body, allow_fallback=True)).json()
    calls = []
    def timeout(*args):
        calls.append("qwen")
        raise httpx.ReadTimeout("simulated lost response")
    monkeypatch.setattr(generation, "call_qwen", timeout)
    monkeypatch.setattr(generation, "call_doubao", lambda *a: pytest.fail("Paid fallback executed"))
    monkeypatch.setattr(generation, "compose_master", lambda *a: None)
    with SessionLocal() as db:
        task = db.get(WorkflowTask, result["task_id"])
        generation.run_generation(db, db.get(StoreProject, project), task, db.get(DesignPlan, plan_id), "qwen", True)
        assert task.status == TaskStatus.NEEDS_USER
        assert task.error_code == "RECONCILING"
        assert task.result["generation_contract"]["plan_hash"] == plan_digest(body)
        assert len(db.scalars(select(ModelCallRecord)).all()) == 1
    assert calls == ["qwen"]
    assert submit(client, project, request(plan_id, body)).json()["replayed"] is True
    assert len(executor) == 1


def test_concurrent_executor_delivery_enters_pipeline_once(client, executor, monkeypatch):
    project, plan_id, body = seed()
    result = submit(client, project, request(plan_id, body)).json()
    entered, release = Event(), Event()
    calls = []
    def fake(db, project, task, plan, provider, fallback):
        calls.append(task.id)
        entered.set()
        assert release.wait(timeout=5)
        task.status = TaskStatus.SUCCEEDED
        db.commit()
    monkeypatch.setattr(generation, "_run_generation", fake)
    def run():
        with SessionLocal() as db:
            generation.run_generation(db, db.get(StoreProject, project), db.get(WorkflowTask, result["task_id"]), db.get(DesignPlan, plan_id), "qwen", False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run)
        assert entered.wait(timeout=5)
        second = pool.submit(run)
        try:
            second.result(timeout=5)
        finally:
            release.set()
        first.result(timeout=5)
    assert calls == [result["task_id"]]


def test_successful_result_keeps_contract_for_future_replay(client, executor, monkeypatch):
    project, plan_id, body = seed()
    result = submit(client, project, request(plan_id, body)).json()
    monkeypatch.setattr(generation, "compose_master", lambda *a: None)
    monkeypatch.setattr(generation, "call_qwen", lambda *a: b"offline-image")
    monkeypatch.setattr(generation, "render_and_slice", lambda *a: {"long_image": "long.png", "slices": []})
    with SessionLocal() as db:
        task = db.get(WorkflowTask, result["task_id"])
        generation.run_generation(db, db.get(StoreProject, project), task, db.get(DesignPlan, plan_id), "qwen", False)
        assert task.status == TaskStatus.SUCCEEDED
        assert task.result["long_image"] == "long.png"
        assert task.result["generation_contract"]["plan_hash"] == plan_digest(body)
    assert submit(client, project, request(plan_id, body)).json()["task_id"] == result["task_id"]
    assert len(executor) == 1
