"""Professional execution binding. No plan selection, model calls or paid retry here."""
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import select, update

from app.models import DesignPlan, StoreProject, TaskStatus, WorkflowTask, utc_now
from app.services.design_plan import validate_design_plan


def plan_digest(plan):
    return sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def reject(code, message, status=409):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def lock_project(db, project_id):
    # Serialize draft edits, confirmation and reservations, including SQLite.
    db.execute(update(StoreProject).where(StoreProject.id == project_id).values(updated_at=utc_now()))


def reserve_generation(db, project, payload):
    lock_project(db, project.id)
    db.refresh(project)
    plan = db.get(DesignPlan, payload.plan_id) if payload.plan_id else db.scalar(
        select(DesignPlan).where(DesignPlan.project_id == project.id).order_by(DesignPlan.version.desc()))
    if plan is None or plan.project_id != project.id:
        reject("PLAN_NOT_FOUND", "指定的设计方案不存在，请重新打开方案。", 404)
    db.refresh(plan)
    if plan.status != "CONFIRMED":
        reject("PLAN_NOT_CONFIRMED", "请先确认设计方案。")
    digest = plan_digest(plan.plan)
    if payload.plan_hash and payload.plan_hash != digest:
        reject("PLAN_CHANGED", "方案已变化，请重新查看并确认；未开始生成。")
    if plan.plan.get("deliverables"):
        reject("BATCH_CONFIRMATION_REQUIRED", "全案或多张详情页请在对应创作中确认项目及调用次数。")
    request_key = payload.request_id or f"default:{plan.id}:{digest}:{payload.provider}"
    tasks = db.scalars(select(WorkflowTask).where(
        WorkflowTask.project_id == project.id,
        WorkflowTask.task_type == "group_buying_image_generation").order_by(WorkflowTask.created_at.desc())).all()
    for task in tasks:
        contract = (task.result or {}).get("generation_contract", {})
        if contract.get("request_key") != request_key:
            continue
        if (contract.get("plan_id"), contract.get("plan_hash"), contract.get("provider")) != (plan.id, digest, payload.provider):
            reject("REQUEST_CONFLICT", "同一次请求不能更换方案或模型；请明确新操作。")
        # Replay returns the original task even if failed/cancelled/finished. Never re-enqueue.
        db.rollback()
        return task, plan, False
    if plan.fact_version != project.current_fact_version:
        reject("FACT_VERSION_CHANGED", "经营事实已更新，请重新审核设计方案；未开始生成。")
    active = next((t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)), None)
    if active:
        reject("GENERATION_IN_PROGRESS", "项目已有生成任务，请查看进度或先停止当前任务。")
    from app.services.worker_status import worker_available
    if not worker_available(db):
        reject("WORKER_UNAVAILABLE", "生成执行器暂未就绪，未创建任务；请稍后再试。", 503)
    try:
        validate_design_plan(plan.plan)
    except (ValueError, KeyError, TypeError) as exc:
        reject("INVALID_DESIGN_PLAN", f"方案检查未通过：{exc}", 422)
    contract = {"version": "professional-generation-v1", "plan_id": plan.id,
                "plan_hash": digest, "fact_version": plan.fact_version,
                "provider": payload.provider, "max_image_calls": 1, "allow_fallback": False,
                "request_key": request_key,
                "binding_mode": "explicit" if payload.plan_id else "legacy_latest"}
    task = WorkflowTask(project_id=project.id, task_type="group_buying_image_generation",
                        result={"design_plan_id": plan.id, "generation_contract": contract})
    db.add(task)
    from app.services.professional_queue import enqueue
    enqueue(db, project, task, plan, contract)
    db.commit()
    return task, plan, True


def execution_matches(contract, project, plan, provider):
    return (contract.get("version") == "professional-generation-v1"
            and contract.get("plan_id") == plan.id
            and getattr(plan, "project_id", None) == project.id
            and plan.status == "CONFIRMED"
            and contract.get("plan_hash") == plan_digest(plan.plan)
            and contract.get("fact_version") == project.current_fact_version == plan.fact_version
            and contract.get("provider") == provider
            and contract.get("max_image_calls") == 1
            and contract.get("allow_fallback") is False)
