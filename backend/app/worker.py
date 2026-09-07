"""Durable single-task worker. Unknown interrupted calls are never retried automatically.

Run from repository root: PYTHONPATH=backend .venv/bin/python -m app.worker
"""
import threading
import time
from datetime import timedelta

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import Creation, CreationConfirmation, DesignPlan, StoreProject, TaskStatus, WorkflowTask, utc_now
from app.services.image_generation import run_generation
from app.services.intake import asset_manifest, selected_assets


def heartbeat(record_id, stop):
    while not stop.wait(15):
        with SessionLocal() as db:
            db.execute(update(CreationConfirmation).where(CreationConfirmation.id == record_id, CreationConfirmation.state == "RUNNING").values(lease_until=utc_now() + timedelta(minutes=5)))
            db.commit()


def run_once():
    with SessionLocal() as db:
        expired = db.scalars(select(CreationConfirmation).where(CreationConfirmation.state == "RUNNING", CreationConfirmation.lease_until < utc_now())).all()
        for record in expired:
            changed = db.execute(update(CreationConfirmation).where(CreationConfirmation.id == record.id, CreationConfirmation.state == "RUNNING", CreationConfirmation.lease_until < utc_now()).values(state="RECONCILING").execution_options(synchronize_session=False))
            if changed.rowcount:
                task = db.get(WorkflowTask, record.task_id)
                if task.status != TaskStatus.SUCCEEDED:
                    task.status = TaskStatus.NEEDS_USER
                    task.error_code = "RECONCILING"
                    task.error_message = "执行中断，远端结果待核对；不会自动重复付费调用"
                else:
                    record.state = "SUCCEEDED"
        db.commit()
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
            record.state = "RECONCILING"
            task.status = TaskStatus.NEEDS_USER
            task.error_code = "RECONCILING"
            task.error_message = "任务未能完成，请核对素材及执行记录；不会自动重复调用"
            db.commit()
        finally:
            stop.set()
            thread.join(timeout=2)
    return True


if __name__ == "__main__":
    while True:
        if not run_once():
            time.sleep(2)
