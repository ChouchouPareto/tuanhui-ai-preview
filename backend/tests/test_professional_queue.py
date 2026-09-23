from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from threading import Event

import pytest
from PIL import Image
from sqlalchemy import delete, select

from app import worker
from app.core.database import SessionLocal
from app.models import (CreationConfirmation, GenerationWorkerHeartbeat, ProfessionalGenerationJob,
                        SourceAsset, TaskStatus, WorkflowTask, utc_now)
from app.services import image_generation as generation
from app.services.professional_queue import recover_expired, run_job
from test_generation_contract import seed, request, submit


def queued(client):
    project, plan, body = seed()
    response = submit(client, project, request(plan, body))
    assert response.status_code == 202, response.text
    with SessionLocal() as db:
        job = db.scalar(select(ProfessionalGenerationJob).where(ProfessionalGenerationJob.task_id == response.json()["task_id"]))
        return project, plan, job.id, job.task_id


def finish(db, project, task, plan, provider, fallback):
    task.status = TaskStatus.SUCCEEDED
    task.result = {**task.result, "long_image": "offline.png"}
    db.commit()


def test_api_only_enqueues_and_worker_picks_after_request_ends(client, monkeypatch):
    monkeypatch.setattr("app.api.execute_generation", lambda *a: pytest.fail("API executed the job"))
    project, plan, job_id, task_id = queued(client)
    with SessionLocal() as db:
        assert db.get(WorkflowTask, task_id).status == TaskStatus.PENDING
        assert db.get(ProfessionalGenerationJob, job_id).state == "QUEUED"
    monkeypatch.setattr(generation, "run_generation", finish)
    assert worker.run_once() is True
    assert worker.run_once() is False
    with SessionLocal() as db:
        assert db.get(ProfessionalGenerationJob, job_id).state == "SUCCEEDED"
        assert db.get(WorkflowTask, task_id).result["long_image"] == "offline.png"


def test_offline_worker_rejects_without_partial_task_or_job(client):
    project, plan, body = seed()
    with SessionLocal() as db:
        db.execute(delete(GenerationWorkerHeartbeat))
        db.commit()
    response = submit(client, project, request(plan, body))
    assert response.status_code == 503
    with SessionLocal() as db:
        assert not db.scalars(select(WorkflowTask)).all()
        assert not db.scalars(select(ProfessionalGenerationJob)).all()


def test_existing_request_is_readable_when_worker_goes_offline(client):
    project, plan, body = seed()
    first = submit(client, project, request(plan, body)).json()
    with SessionLocal() as db:
        db.execute(delete(GenerationWorkerHeartbeat))
        db.commit()
    replay = submit(client, project, request(plan, body))
    assert replay.status_code == 202
    assert replay.json()["task_id"] == first["task_id"]


@pytest.mark.parametrize("task_state", [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.FAILED_FINAL])
def test_expired_lease_never_requeues_and_preserves_terminal_results(client, monkeypatch, task_state):
    _, _, job_id, task_id = queued(client)
    with SessionLocal() as db:
        job = db.get(ProfessionalGenerationJob, job_id)
        job.state, job.lease_token, job.lease_until = "RUNNING", "dead-worker", utc_now() - timedelta(minutes=1)
        task = db.get(WorkflowTask, task_id)
        task.status = task_state
        task.result = {**task.result, "keep": "old-result"}
        db.commit()
        assert recover_expired(db) == 1
        db.refresh(task)
        db.refresh(job)
        assert task.result["keep"] == "old-result"
        if task_state in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            assert task.status == TaskStatus.NEEDS_USER and task.error_code == "RECONCILING"
        else:
            assert task.status == task_state
        assert job.state != "QUEUED"
    monkeypatch.setattr(generation, "run_generation", lambda *a: pytest.fail("Unknown request was retried"))
    assert worker.run_once() is False


def test_stop_queued_job_prevents_claim(client, monkeypatch):
    _, _, job_id, task_id = queued(client)
    assert client.post(f"/api/v1/tasks/{task_id}/pause").status_code == 200
    monkeypatch.setattr(generation, "run_generation", lambda *a: pytest.fail("Stopped job executed"))
    assert run_job(job_id) is False
    with SessionLocal() as db:
        assert db.get(ProfessionalGenerationJob, job_id).state == "PAUSED"


def test_duplicate_worker_claim_executes_once(client, monkeypatch):
    _, _, job_id, _ = queued(client)
    started, release = Event(), Event()
    calls = []
    def slow(*args):
        calls.append(1)
        started.set()
        assert release.wait(5)
        finish(*args)
    monkeypatch.setattr(generation, "run_generation", slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run_job, job_id)
        assert started.wait(5)
        try:
            assert pool.submit(run_job, job_id).result(5) is False
        finally:
            release.set()
        assert first.result(5) is True
    assert calls == [1]


def test_asset_bytes_changed_after_enqueue_prevents_model(client, monkeypatch, tmp_path):
    project, plan, body = seed()
    buf = BytesIO()
    Image.new("RGB", (800,600), "white").save(buf, format="PNG")
    response = client.post(f"/api/v1/projects/{project}/assets", data={"asset_type":"product", "semantic_role":"dish"},
                           files={"file":("dish.png", buf.getvalue(), "image/png")})
    assert response.status_code == 201
    result = submit(client, project, request(plan, body)).json()
    with SessionLocal() as db:
        asset = db.get(SourceAsset, response.json()["asset_id"])
        from pathlib import Path
        # A test-owned upload, never a user file.
        Path(asset.storage_path).write_bytes(b"changed-fixture")
        job_id = db.scalar(select(ProfessionalGenerationJob.id).where(ProfessionalGenerationJob.task_id == result["task_id"]))
    monkeypatch.setattr(generation, "run_generation", lambda *a: pytest.fail("Changed asset was sent"))
    assert run_job(job_id)
    with SessionLocal() as db:
        task = db.get(WorkflowTask, result["task_id"])
        assert task.status == TaskStatus.NEEDS_USER
        assert task.error_code == "EXECUTION_INPUT_CHANGED"


def test_input_failure_rolls_back_task_and_job_together(client, monkeypatch):
    project, plan, body = seed()
    monkeypatch.setattr("app.services.professional_queue.freeze_assets", lambda *a: (_ for _ in ()).throw(ValueError("fixture")))
    assert submit(client, project, request(plan, body)).status_code == 500
    with SessionLocal() as db:
        assert not db.scalars(select(WorkflowTask)).all()
        assert not db.scalars(select(ProfessionalGenerationJob)).all()


def test_failure_after_committed_success_does_not_destroy_result(client, monkeypatch):
    _, _, job_id, task_id = queued(client)
    def interrupted(*args):
        finish(*args)
        raise RuntimeError("process boundary after commit")
    monkeypatch.setattr(generation, "run_generation", interrupted)
    run_job(job_id)
    with SessionLocal() as db:
        assert db.get(WorkflowTask, task_id).status == TaskStatus.SUCCEEDED
        assert db.get(ProfessionalGenerationJob, job_id).state == "SUCCEEDED"


def test_late_model_response_does_not_overwrite_reconciliation(client, monkeypatch):
    _, _, job_id, task_id = queued(client)
    def lose_lease(*args):
        with SessionLocal() as db:
            job = db.get(ProfessionalGenerationJob, job_id)
            job.lease_until = utc_now() - timedelta(minutes=1)
            db.commit()
            assert recover_expired(db) == 1
        return b"late-model-image"
    monkeypatch.setattr(generation, "call_qwen", lose_lease)
    monkeypatch.setattr(generation, "compose_master", lambda *a: None)
    monkeypatch.setattr(generation, "render_and_slice", lambda *a: pytest.fail("Late model output published"))
    run_job(job_id)
    with SessionLocal() as db:
        task = db.get(WorkflowTask, task_id)
        assert task.status == TaskStatus.NEEDS_USER and task.error_code == "RECONCILING"
        assert db.get(ProfessionalGenerationJob, job_id).state == "RECONCILING"


def test_new_table_migration_is_additive_and_repeatable(tmp_path):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    file = Path(__file__).parents[1] / "alembic/versions/f4d8b0c2e6a1_professional_generation_queue.py"
    spec = importlib.util.spec_from_file_location("professional_queue_migration", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE keep_history (id TEXT PRIMARY KEY)")
        conn.exec_driver_sql("INSERT INTO keep_history VALUES ('original')")
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            module.upgrade()
        assert "professional_generation_jobs" in inspect(conn).get_table_names()
        assert conn.exec_driver_sql("SELECT id FROM keep_history").scalar() == "original"
    engine.dispose()


def test_stop_during_model_call_does_not_publish_late_output(client, monkeypatch):
    _, _, job_id, task_id = queued(client)
    def stopped(*args):
        assert client.post(f"/api/v1/tasks/{task_id}/pause").status_code == 200
        return b"late-result"
    monkeypatch.setattr(generation, "call_qwen", stopped)
    monkeypatch.setattr(generation, "compose_master", lambda *a: None)
    monkeypatch.setattr(generation, "render_and_slice", lambda *a: pytest.fail("Stopped result published"))
    run_job(job_id)
    with SessionLocal() as db:
        task = db.get(WorkflowTask, task_id)
        assert task.status == TaskStatus.NEEDS_USER and task.error_code == "PAUSED_BY_USER"
        assert db.get(ProfessionalGenerationJob, job_id).state == "PAUSED"


@pytest.mark.parametrize("task_state", [TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.FAILED_FINAL])
def test_busy_professional_queue_still_recovers_creation_leases(client, monkeypatch, task_state):
    from test_m1_creations import setup_creation, submit as intake, confirm
    _, asset, base = setup_creation(client)
    task_id = confirm(client, base, intake(client, base, asset).json()).json()["task_id"]
    with SessionLocal() as db:
        record = db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id == task_id))
        record.state, record.lease_until = "RUNNING", utc_now() - timedelta(minutes=1)
        db.get(WorkflowTask, task_id).status = task_state
        db.commit()
    queued(client)
    monkeypatch.setattr(generation, "run_generation", finish)
    assert worker.run_once()
    with SessionLocal() as db:
        task = db.get(WorkflowTask, task_id)
        assert task.status == (TaskStatus.NEEDS_USER if task_state == TaskStatus.RUNNING else task_state)
        record = db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id == task_id))
        assert record.state == ("RECONCILING" if task_state == TaskStatus.RUNNING else task_state.value)


def test_oldest_creation_is_served_before_new_professional_job(client, monkeypatch):
    from test_m1_creations import setup_creation, submit as intake, confirm
    _, asset, base = setup_creation(client)
    first_task = confirm(client, base, intake(client, base, asset).json()).json()["task_id"]
    _, _, job_id, _ = queued(client)
    calls = []
    def creation_finish(*args):
        calls.append(args[2].id)
        finish(*args)
    monkeypatch.setattr(worker, "run_generation", creation_finish)
    assert worker.run_once()
    assert calls == [first_task]
    with SessionLocal() as db:
        assert db.get(ProfessionalGenerationJob, job_id).state == "QUEUED"


def test_creation_exception_after_success_preserves_committed_result(client, monkeypatch):
    from test_m1_creations import setup_creation, submit as intake, confirm
    _, asset, base = setup_creation(client)
    task_id = confirm(client, base, intake(client, base, asset).json()).json()["task_id"]
    def interrupt(*args):
        finish(*args)
        raise RuntimeError("interrupted after success commit")
    monkeypatch.setattr(worker, "run_generation", interrupt)
    assert worker.run_once()
    with SessionLocal() as db:
        assert db.get(WorkflowTask, task_id).status == TaskStatus.SUCCEEDED
        record = db.scalar(select(CreationConfirmation).where(CreationConfirmation.task_id == task_id))
        assert record.state == "SUCCEEDED"
