"""Durable single-task worker. Unknown interrupted calls are never retried automatically.

Run from repository root: PYTHONPATH=backend .venv/bin/python -m app.worker
"""
import threading
import time
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.core.database import Base, engine
from app.models import GenerationWorkerHeartbeat
from app.models import Creation, CreationConfirmation, DesignPlan, StoreProject, TaskStatus, WorkflowTask, utc_now
from app.services.image_generation import run_generation
from app.services.intake import asset_manifest, selected_assets


def heartbeat(record_id, stop):
    while not stop.wait(15):
        with SessionLocal() as db:
            db.execute(update(CreationConfirmation).where(CreationConfirmation.id == record_id, CreationConfirmation.state == "RUNNING").values(lease_until=utc_now() + timedelta(minutes=5)))
            db.commit()


def recover_creations(db):
    """Reconcile lost leases even while the professional queue is busy."""
    from app.services.professional_queue import terminal_state
    expired = db.scalars(select(CreationConfirmation).where(
        CreationConfirmation.state == "RUNNING", CreationConfirmation.lease_until < utc_now())).all()
    for record in expired:
        changed = db.execute(update(CreationConfirmation).where(
            CreationConfirmation.id == record.id, CreationConfirmation.state == "RUNNING",
            CreationConfirmation.lease_until < utc_now()).values(state="RECONCILING", lease_until=None)
            .execution_options(synchronize_session=False))
        if changed.rowcount:
            task = db.get(WorkflowTask, record.task_id)
            if task:
                db.execute(update(WorkflowTask).where(WorkflowTask.id == task.id,
                    WorkflowTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])).values(
                    status=TaskStatus.NEEDS_USER, error_code="RECONCILING",
                    error_message="执行中断，远端结果待核对；不会自动重复付费调用")
                    .execution_options(synchronize_session=False))
                db.refresh(task)
            db.execute(update(CreationConfirmation).where(CreationConfirmation.id == record.id)
                       .values(state=terminal_state(task) if task else "RECONCILING")
                       .execution_options(synchronize_session=False))
    db.commit()


def run_creation_once():
    with SessionLocal() as db:
        recover_creations(db)
        record = db.scalar(select(CreationConfirmation).where(CreationConfirmation.state == "QUEUED").order_by(CreationConfirmation.created_at))
        if not record:
            return False
        claimed = db.execute(update(CreationConfirmation).where(CreationConfirmation.id == record.id, CreationConfirmation.state == "QUEUED").values(state="RUNNING", lease_until=utc_now() + timedelta(minutes=5)))
        db.commit()
        if not claimed.rowcount:
            return True
        task = db.get(WorkflowTask, record.task_id)
        if task.status != TaskStatus.PENDING:
            record.state = "PAUSED" if task.status == TaskStatus.NEEDS_USER else "RECONCILING"
            db.commit()
            return True
        stop = threading.Event()
        thread = threading.Thread(target=heartbeat, args=(record.id, stop), daemon=True)
        thread.start()
        try:
            creation = db.get(Creation, record.creation_id)
            assets = selected_assets(db, creation.project_id, [a["id"] for a in record.snapshot["assets"]])
            if asset_manifest(assets) != record.snapshot["assets"]:
                raise ValueError("素材变化")
            run_generation(db, db.get(StoreProject, creation.project_id), task, db.get(DesignPlan, record.plan_id), record.snapshot["provider"], False)
            db.refresh(task)
            record.state = task.status.value
            # A provider failure can represent a lost response; do not offer automatic retry.
            if task.status == TaskStatus.FAILED_FINAL and task.error_code == "ALL_PROVIDERS_FAILED":
                record.state = "RECONCILING"
                task.status = TaskStatus.NEEDS_USER
                task.error_code = "RECONCILING"
                task.error_message = "生成未确认成功，请核对供应商记录；不会自动重试或切换模型"
            db.commit()
        except Exception:
            db.rollback()
            record = db.get(CreationConfirmation, record.id)
            task = db.get(WorkflowTask, record.task_id)
            from app.services.professional_queue import terminal_state
            db.execute(update(WorkflowTask).where(WorkflowTask.id == task.id,
                WorkflowTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])).values(
                status=TaskStatus.NEEDS_USER, error_code="RECONCILING",
                error_message="任务未能完成，请核对素材及执行记录；不会自动重复调用")
                .execution_options(synchronize_session=False))
            db.refresh(task)
            record.state = terminal_state(task)
            record.lease_until = None
            db.commit()
        finally:
            stop.set()
            thread.join(timeout=2)
    return True


def run_once():
    from app.models import ProfessionalGenerationJob, AgentRun
    from app.services import agent_runtime
    from app.services.professional_queue import recover_expired, run_job
    with SessionLocal() as db:
        recover_expired(db)
        recover_creations(db)
        agent_runtime.recover(db)
        agent = db.scalar(select(AgentRun).where(AgentRun.state == "QUEUED").order_by(AgentRun.created_at))
        professional = db.scalar(select(ProfessionalGenerationJob).where(
            ProfessionalGenerationJob.state == "QUEUED").order_by(ProfessionalGenerationJob.created_at))
        creation = db.scalar(select(CreationConfirmation).where(
            CreationConfirmation.state == "QUEUED").order_by(CreationConfirmation.created_at))
        job_id = professional.id if professional and (not creation or professional.created_at <= creation.created_at) else None
        oldest_image = min([j.created_at for j in (professional, creation) if j], default=None)
        agent_id = agent.id if agent and (oldest_image is None or agent.created_at <= oldest_image) else None
    if agent_id:
        agent_runtime.run_job(agent_id)
        return True
    # Oldest ready job across both entry points. Neither queue starves the other.
    if job_id:
        run_job(job_id)
        return True
    return run_creation_once()


def serve():
    Base.metadata.create_all(engine)
    worker_id = str(uuid.uuid4())
    stopped = threading.Event()
    def announce():
        with SessionLocal() as db:
            db.merge(GenerationWorkerHeartbeat(id=worker_id, updated_at=utc_now()))
            db.commit()
    def pulse():
        while not stopped.wait(10):
            announce()
    announce()
    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        while True:
            if not run_once():
                time.sleep(2)
    finally:
        stopped.set()
        thread.join(timeout=2)
        with SessionLocal() as db:
            record = db.get(GenerationWorkerHeartbeat, worker_id)
            if record:
                db.delete(record)
                db.commit()


if __name__ == "__main__":
    serve()
