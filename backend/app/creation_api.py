from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Creation, CreationConfirmation, DesignPlan, IntakeRevision, StoreProject, WorkflowTask, utc_now
from app.services.design_plan import build_design_plan
from app.services.worker_status import worker_available
from app.services.intake import (CreateInput, IntakeInput, ConfirmInput, asset_manifest, compile_intake,
                                 digest, fail, require_creation, review, selected_assets)

router = APIRouter(prefix="/api/v1/projects/{project_id}/creations", tags=["M1 creations"])


@router.post("", status_code=201)
def create(project_id: str, payload: CreateInput, db: Session = Depends(get_db)):
    if not db.get(StoreProject, project_id):
        fail("NOT_FOUND", "项目不存在", 404)
    item = Creation(project_id=project_id, mode=payload.mode)
    db.add(item)
    db.commit()
    return review(db, item)


@router.get("/{creation_id}/review")
def get_review(project_id: str, creation_id: str, db: Session = Depends(get_db)):
    creation = require_creation(db, project_id, creation_id)
    result = review(db, creation)
    confirmation = db.scalar(select(CreationConfirmation).where(CreationConfirmation.creation_id == creation_id, CreationConfirmation.revision == creation.revision))
    result["task_id"] = confirmation.task_id if confirmation else None
    result["execution_state"] = confirmation.state if confirmation else None
    return result


@router.post("/{creation_id}/intake-runs")
def intake(project_id: str, creation_id: str, payload: IntakeInput,
           idempotency_key: str = Header(min_length=1, max_length=120), db: Session = Depends(get_db)):
    creation = require_creation(db, project_id, creation_id)
    request_hash = digest(payload.model_dump())
    previous = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation_id, IntakeRevision.request_key == idempotency_key))
    if previous:
        if previous.request_hash != request_hash:
            fail("IDEMPOTENCY_CONFLICT", "同一请求标识不能提交不同内容")
        return review(db, creation)
    if creation.status == "CONFIRMED":
        fail("CREATION_LOCKED", "本次已确认，请继续创作建立新任务；旧作品会保留")
    if creation.revision != payload.expected_revision:
        fail("STALE_REVISION", "资料已更新，请刷新后重新检查")
    snapshot = compile_intake(db, creation, payload)
    next_revision = creation.revision + 1
    changed = db.execute(update(Creation).where(Creation.id == creation_id, Creation.revision == payload.expected_revision, Creation.status != "CONFIRMED").values(revision=next_revision, status="READY_TO_CONFIRM" if snapshot["ready"] else "NEEDS_INPUT"))
    if changed.rowcount != 1:
        db.rollback()
        fail("STALE_REVISION", "资料已更新，请刷新后重新检查")
    db.add(IntakeRevision(creation_id=creation_id, revision=next_revision, request_key=idempotency_key,
                         request_hash=request_hash, snapshot=snapshot, snapshot_hash=digest(snapshot)))
    db.commit()
    db.refresh(creation)
    return review(db, creation)


@router.post("/{creation_id}/confirm")
def confirm(project_id: str, creation_id: str, payload: ConfirmInput,
            idempotency_key: str = Header(min_length=1, max_length=120), db: Session = Depends(get_db)):
    creation = require_creation(db, project_id, creation_id)
    item = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation_id, IntakeRevision.revision == creation.revision))
    if not item or creation.revision != payload.expected_revision or item.snapshot_hash != payload.snapshot_hash:
        fail("STALE_REVISION", "确认内容已过期，请重新检查")
    existing = db.scalar(select(CreationConfirmation).where(CreationConfirmation.creation_id == creation_id, CreationConfirmation.revision == creation.revision))
    if existing:
        return {"confirmation_id": existing.id, "task_id": existing.task_id, "state": existing.state}
    snapshot = item.snapshot
    if not snapshot["ready"]:
        fail("INPUT_INCOMPLETE", "请先补充必要信息")
    if not payload.materials_confirmed:
        fail("MATERIALS_NOT_CONFIRMED", "请确认所选菜品与名称一致，并拥有素材使用权")
    assets = selected_assets(db, project_id, [a["id"] for a in snapshot["assets"]])
    if asset_manifest(assets) != snapshot["assets"]:
        fail("ASSETS_CHANGED", "素材分类或内容已变化，请重新提交资料")
    if not worker_available(db):
        fail("WORKER_UNAVAILABLE", "生图服务暂未就绪，需求已保留，尚未启动生图。请稍后再试。", 503)
    changed = db.execute(update(Creation).where(Creation.id == creation_id, Creation.revision == payload.expected_revision, Creation.status == "READY_TO_CONFIRM").values(status="CONFIRMED"))
    if changed.rowcount != 1:
        db.rollback()
        fail("CONFIRMATION_CONFLICT", "本次确认已被处理，请刷新查看任务")
    facts = dict(snapshot["facts"])
    if isinstance(facts.get("selling_points"), str):
        facts["selling_points"] = [facts["selling_points"]] if facts["selling_points"] else []
    facts.update(show_price=snapshot["show_price"], show_store_name=snapshot["show_store_name"])
    plan_data = build_design_plan(facts, snapshot["style"])
    plan_data["render_mode"] = snapshot.get("render_mode", "real_assets")
    plan_data["selected_asset_ids"] = [a["id"] for a in snapshot["assets"] if a["usage"] == "renderable"]
    plan_data["creation_id"] = creation_id
    version = (db.scalar(select(func.max(DesignPlan.version)).where(DesignPlan.project_id == project_id)) or 0) + 1
    plan = DesignPlan(project_id=project_id, fact_version=0, version=version, status="CONFIRMED", plan=plan_data, confirmed_at=utc_now())
    task = WorkflowTask(project_id=project_id, task_type="group_buying_image_generation", result={"creation_id": creation_id})
    db.add_all([plan, task])
    db.flush()
    record = CreationConfirmation(creation_id=creation_id, revision=creation.revision, request_key=idempotency_key,
                                  snapshot=snapshot, plan_id=plan.id, task_id=task.id)
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("CONFIRMATION_CONFLICT", "确认已处理，请刷新查看任务")
    return {"confirmation_id": record.id, "task_id": task.id, "state": record.state}
