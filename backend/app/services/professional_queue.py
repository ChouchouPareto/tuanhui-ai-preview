"""Durable professional jobs. Claimed/unknown requests are never automatically replayed."""
from datetime import timedelta
import threading
import uuid

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import (DesignPlan, ProfessionalGenerationJob, SourceAsset, StoreProject,
                        TaskStatus, WorkflowTask, utc_now)
from app.services.intake import asset_manifest, selected_assets


def freeze_assets(db, project_id, plan):
    assets = db.scalars(select(SourceAsset).where(SourceAsset.project_id == project_id)
                       .order_by(SourceAsset.is_hero.desc(), SourceAsset.priority, SourceAsset.created_at, SourceAsset.id)).all()
    if "selected_asset_ids" in plan:
        ids = plan["selected_asset_ids"]
        selected_assets(db, project_id, ids)  # Reject missing/foreign IDs, not just filter them away.
        assets = [a for a in assets if a.id in ids]
    selected_assets(db, project_id, [a.id for a in assets])  # Verify bytes before reserving any call.
    return [{**entry, "priority": asset.priority, "is_hero": asset.is_hero,
             "asset_type": asset.asset_type} for entry, asset in zip(asset_manifest(assets), assets)]


def enqueue(db, project, task, plan, contract):
    db.flush()
    job = ProfessionalGenerationJob(project_id=project.id, task_id=task.id, plan_id=plan.id,
        snapshot={"contract": dict(contract), "assets": freeze_assets(db, project.id, plan.plan)})
    db.add(job)
    return job


def terminal_state(task):
    if task.status == TaskStatus.NEEDS_USER:
        return "PAUSED" if task.error_code == "PAUSED_BY_USER" else "RECONCILING"
    return task.status.value


def recover_expired(db):
    jobs = db.scalars(select(ProfessionalGenerationJob).where(
        ProfessionalGenerationJob.state == "RUNNING",
        ProfessionalGenerationJob.lease_until < utc_now())).all()
    recovered = 0
    for job in jobs:
        won = db.execute(update(ProfessionalGenerationJob).where(
            ProfessionalGenerationJob.id == job.id, ProfessionalGenerationJob.state == "RUNNING",
            ProfessionalGenerationJob.lease_token == job.lease_token,
            ProfessionalGenerationJob.lease_until < utc_now()).values(state="RECONCILING", lease_until=None)
            .execution_options(synchronize_session=False))
        if not won.rowcount:
            continue
        task = db.get(WorkflowTask, job.task_id)
        if task and task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            db.execute(update(WorkflowTask).where(WorkflowTask.id == task.id,
                WorkflowTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])).values(
                    status=TaskStatus.NEEDS_USER, error_code="RECONCILING",
                    error_message="执行中断，远端结果待核对；不会自动重新生成或重复付费。")
                .execution_options(synchronize_session=False))
            db.refresh(task)
        db.flush()
        # Persisted terminal results survive a crash between task and job commits.
        db.execute(update(ProfessionalGenerationJob).where(ProfessionalGenerationJob.id == job.id)
                   .values(state=terminal_state(task) if task else "RECONCILING")
                   .execution_options(synchronize_session=False))
        recovered += 1
    db.commit()
    return recovered


def pulse(job_id, token, stop):
    while not stop.wait(15):
        with SessionLocal() as db:
            touched = db.execute(update(ProfessionalGenerationJob).where(
                ProfessionalGenerationJob.id == job_id, ProfessionalGenerationJob.state == "RUNNING",
                ProfessionalGenerationJob.lease_token == token).values(lease_until=utc_now() + timedelta(minutes=5)))
            db.commit()
            if not touched.rowcount:
                return


def run_job(job_id):
    from app.services.image_generation import run_generation
    token = str(uuid.uuid4())
    with SessionLocal() as db:
        won = db.execute(update(ProfessionalGenerationJob).where(
            ProfessionalGenerationJob.id == job_id, ProfessionalGenerationJob.state == "QUEUED"
        ).values(state="RUNNING", lease_token=token, lease_until=utc_now() + timedelta(minutes=5)))
        db.commit()
        if not won.rowcount:
            return False
        job = db.get(ProfessionalGenerationJob, job_id)
        task = db.get(WorkflowTask, job.task_id)
        if not task or task.status != TaskStatus.PENDING:
            job.state = terminal_state(task) if task else "RECONCILING"
            job.lease_until = None
            db.commit()
            return True
        stop = threading.Event()
        thread = threading.Thread(target=pulse, args=(job_id, token, stop), daemon=True)
        thread.start()
        execution_started = False
        try:
            project, plan = db.get(StoreProject, job.project_id), db.get(DesignPlan, job.plan_id)
            if (not project or not plan or plan.project_id != project.id or task.project_id != project.id
                    or task.result.get("generation_contract") != job.snapshot["contract"]):
                raise ValueError("Execution binding changed")
            if freeze_assets(db, project.id, plan.plan) != job.snapshot["assets"]:
                raise ValueError("Asset snapshot changed")
            execution_started = True
            run_generation(db, project, task, plan, job.snapshot["contract"]["provider"], False)
        except Exception:
            db.rollback()
            task = db.get(WorkflowTask, job.task_id)
            # Do not turn a committed success, failure or user stop into another result.
            if task and task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
                db.execute(update(WorkflowTask).where(WorkflowTask.id == task.id,
                    WorkflowTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])).values(
                    status=TaskStatus.NEEDS_USER,
                    error_code="RECONCILING" if execution_started else "EXECUTION_INPUT_CHANGED",
                    error_message=("执行记录需要核对；未自动重试、切换模型或覆盖旧作品。" if execution_started
                                   else "素材或执行绑定已变化，未调用生图模型；请重新审核。"))
                    .execution_options(synchronize_session=False))
                db.commit()
        finally:
            stop.set()
            thread.join(timeout=2)
            if task:
                db.refresh(task)
            db.execute(update(ProfessionalGenerationJob).where(
                ProfessionalGenerationJob.id == job_id, ProfessionalGenerationJob.state == "RUNNING",
                ProfessionalGenerationJob.lease_token == token).values(state=terminal_state(task) if task else "RECONCILING", lease_until=None))
            db.commit()
    return True
