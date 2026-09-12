import uuid
import copy
from typing import Literal
from pydantic import BaseModel, Field
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models import ClarificationRound, DesignPlan, FactVersion, ProjectStatus, SourceAsset, StoreProject, TaskStatus, WorkflowTask, utc_now
from app.schemas import AnalysisRunRequest, AssetMetadataUpdate, ClarificationSubmit, DesignPlanConfirm, DesignPlanCreate, DesignPlanUpdate, FactConfirm, FactUpdate, GenerationRunRequest, ProjectCreate
from app.services.analysis import coverage_for, merge_answers, run_analysis, run_dialogue_intake
from app.services.design_plan import build_design_plan, update_design_plan
from app.services.image_generation import run_generation
from app.services.storage import store_upload
from app.models import ProjectDisplayState, Creation, CreationConfirmation, IntakeRevision


router = APIRouter(prefix="/api/v1")


def require_project(db: Session, project_id: str) -> StoreProject:
    project = db.get(StoreProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = StoreProject(name=payload.name.strip(), industry=payload.industry, platforms=payload.platforms)
    db.add(project)
    db.commit()
    return {"project_id": project.id, "status": project.status}


@router.get("/projects")
def list_projects(visibility: Literal["visible", "hidden", "deleted"] = "visible", db: Session = Depends(get_db)):
    projects = db.scalars(select(StoreProject).order_by(StoreProject.updated_at.desc())).all()
    result = []
    for project in projects:
        display = db.get(ProjectDisplayState, project.id)
        if (display.visibility if display else "visible") != visibility:
            continue
        tasks = db.scalars(select(WorkflowTask).where(WorkflowTask.project_id == project.id, WorkflowTask.task_type == "group_buying_image_generation").order_by(WorkflowTask.created_at.desc())).all()
        cover = next((t for t in tasks if t.status == TaskStatus.SUCCEEDED and (t.result or {}).get("long_image")), None)
        result.append({"id": project.id, "name": project.name, "status": project.status,
                       "updated_at": project.updated_at, "task_count": len(tasks),
                       "cover": f"/projects/{project.id}/generations/{cover.id}/assets/{cover.result['long_image']}" if cover else None})
    return result


class ProjectEdit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    visibility: Literal["visible", "hidden", "deleted"] | None = None


@router.patch("/projects/{project_id}")
def edit_project(project_id: str, payload: ProjectEdit, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    display = db.get(ProjectDisplayState, project_id) or ProjectDisplayState(project_id=project_id)
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(422, "项目名称不能为空")
        project.name = payload.name.strip()
        display.custom_name = True
    if payload.visibility:
        if payload.visibility == "deleted" and db.scalar(select(WorkflowTask.id).where(WorkflowTask.project_id == project_id, WorkflowTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])).limit(1)):
            raise HTTPException(409, "项目仍有运行中的任务，请先停止任务再移入回收站")
        display.visibility = payload.visibility
    project.updated_at = utc_now()
    db.add(display)
    db.commit()
    return {"id": project.id, "name": project.name, "visibility": display.visibility}


@router.post("/projects/{project_id}/duplicate", status_code=201)
def duplicate_project(project_id: str, db: Session = Depends(get_db)):
    original = require_project(db, project_id)
    project = StoreProject(name=original.name[:115] + " · 副本", industry=original.industry, platforms=copy.deepcopy(original.platforms))
    db.add(project)
    db.flush()
    for asset in db.scalars(select(SourceAsset).where(SourceAsset.project_id == project_id)).all():
        values = {column.name: copy.deepcopy(getattr(asset, column.name)) for column in SourceAsset.__table__.columns if column.name not in {"id", "project_id", "created_at"}}
        db.add(SourceAsset(project_id=project.id, **values))
    fact = db.scalar(select(FactVersion).where(FactVersion.project_id == project_id).order_by(FactVersion.version.desc()))
    if fact:
        values = {column.name: copy.deepcopy(getattr(fact, column.name)) for column in FactVersion.__table__.columns if column.name not in {"id", "project_id", "created_at", "version"}}
        db.add(FactVersion(project_id=project.id, version=1, **values))
        project.current_fact_version = 1
    else:
        revision = db.scalar(select(IntakeRevision).join(Creation, Creation.id == IntakeRevision.creation_id).where(Creation.project_id == project_id).order_by(IntakeRevision.created_at.desc()).limit(1))
        if revision:
            db.add(FactVersion(project_id=project.id, version=1, facts=copy.deepcopy(revision.snapshot.get("facts", {}))))
            project.current_fact_version = 1
    db.add(ProjectDisplayState(project_id=project.id, custom_name=True))
    db.commit()
    return {"project_id": project.id, "name": project.name}


@router.get("/projects/{project_id}/workspace")
def project_workspace(project_id: str, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    tasks = db.scalars(select(WorkflowTask).where(WorkflowTask.project_id == project_id, WorkflowTask.task_type == "group_buying_image_generation").order_by(WorkflowTask.created_at.desc())).all()
    fact = db.scalar(select(FactVersion).where(FactVersion.project_id == project_id).order_by(FactVersion.version.desc()))
    plan = db.scalar(select(DesignPlan).where(DesignPlan.project_id == project_id).order_by(DesignPlan.version.desc()))
    return {"id": project.id, "name": project.name, "facts": fact.facts if fact else {},
            "latest_creation_id": db.scalar(select(Creation.id).where(Creation.project_id == project_id).order_by(Creation.created_at.desc()).limit(1)),
            "style": plan.plan.get("style") if plan else None,
            "tasks": [{"id": t.id, "status": t.status, "created_at": t.created_at,
                       "progress": t.progress, "result": t.result or {}, "error": t.error_message} for t in tasks]}


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    return {"id": project.id, "name": project.name, "industry": project.industry, "platforms": project.platforms, "status": project.status, "current_fact_version": project.current_fact_version}


@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str, db: Session = Depends(get_db)):
    require_project(db, project_id)
    assets = db.scalars(select(SourceAsset).where(SourceAsset.project_id == project_id).order_by(SourceAsset.priority, SourceAsset.created_at)).all()
    return [{"id": item.id, "asset_type": item.asset_type, "semantic_role": item.semantic_role, "subcategory": item.subcategory, "priority": item.priority, "is_hero": item.is_hero, "original_name": item.original_name, "quality": item.quality, "width": item.width, "height": item.height, "preview_path": f"/projects/{project_id}/assets/{item.id}/content"} for item in assets]


@router.get("/projects/{project_id}/assets/{asset_id}/content")
def preview_asset(project_id: str, asset_id: str, db: Session = Depends(get_db)):
    require_project(db, project_id)
    asset = db.get(SourceAsset, asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="素材不存在")
    path = Path(asset.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="素材文件不存在")
    return FileResponse(path, media_type=asset.mime_type, headers={"Cache-Control": "private, max-age=3600"})


@router.post("/projects/{project_id}/assets", status_code=201)
def upload_asset(project_id: str, asset_type: str = Form(...), semantic_role: str | None = Form(None), subcategory: str | None = Form(None), priority: int = Form(100), is_hero: bool = Form(False), file: UploadFile = File(...), db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    if asset_type not in {"menu", "storefront", "product", "environment", "logo", "credential", "other"}:
        raise HTTPException(status_code=422, detail="不支持的素材类型")
    allowed_roles = {"storefront", "menu", "signature_dish", "dish", "environment", "logo", "credential", "other"}
    role = semantic_role or {"product": "dish"}.get(asset_type, asset_type)
    if role not in allowed_roles:
        raise HTTPException(status_code=422, detail="不支持的素材角色")
    if not 1 <= priority <= 999:
        raise HTTPException(status_code=422, detail="素材优先级必须在1到999之间")
    normalized_subcategory = subcategory.strip() if subcategory else None
    if normalized_subcategory and len(normalized_subcategory) > 60:
        raise HTTPException(status_code=422, detail="素材小分类不能超过60个字符")
    if is_hero:
        for current in db.scalars(select(SourceAsset).where(SourceAsset.project_id == project_id, SourceAsset.is_hero.is_(True))).all():
            current.is_hero = False
    normalized_type = role if role in {"menu", "storefront"} else asset_type
    asset = SourceAsset(project_id=project_id, asset_type=normalized_type, semantic_role=role, subcategory=normalized_subcategory, priority=priority, is_hero=is_hero, original_name=file.filename or "upload", storage_path="", mime_type=file.content_type or "", byte_size=0, sha256="")
    db.add(asset)
    db.flush()
    try:
        stored = store_upload(project_id, asset.id, file)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    asset.storage_path = stored["path"]
    asset.byte_size = stored["size"]
    asset.sha256 = stored["sha256"]
    asset.width = stored["width"]
    asset.height = stored["height"]
    asset.quality = stored["quality"]
    project.status = ProjectStatus.ASSETS_UPLOADED
    db.commit()
    return {"asset_id": asset.id, "asset_type": asset.asset_type, "semantic_role": asset.semantic_role, "subcategory": asset.subcategory, "priority": asset.priority, "is_hero": asset.is_hero, "quality": asset.quality, "width": asset.width, "height": asset.height}


@router.patch("/projects/{project_id}/assets/{asset_id}")
def update_asset_metadata(project_id: str, asset_id: str, payload: AssetMetadataUpdate, db: Session = Depends(get_db)):
    require_project(db, project_id)
    asset = db.get(SourceAsset, asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="素材不存在")
    values = payload.model_dump(exclude_none=True)
    if values.get("is_hero"):
        for current in db.scalars(select(SourceAsset).where(SourceAsset.project_id == project_id, SourceAsset.is_hero.is_(True), SourceAsset.id != asset_id)).all():
            current.is_hero = False
    for key, value in values.items():
        setattr(asset, key, value)
    db.commit()
    return {"asset_id": asset.id, "semantic_role": asset.semantic_role, "subcategory": asset.subcategory, "priority": asset.priority, "is_hero": asset.is_hero}


def execute_analysis(project_id: str, task_id: str, use_ai: bool):
    with SessionLocal() as db:
        project = db.get(StoreProject, project_id)
        task = db.get(WorkflowTask, task_id)
        if project and task:
            if use_ai:
                run_analysis(db, project, task)
            else:
                run_dialogue_intake(db, project, task)


@router.post("/projects/{project_id}/analysis-runs", status_code=202)
def start_analysis(project_id: str, background: BackgroundTasks, payload: AnalysisRunRequest | None = None, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    roles = set(db.scalars(select(SourceAsset.semantic_role).where(SourceAsset.project_id == project_id)).all())
    has_store_asset = bool(roles & {"storefront", "environment", "logo"})
    has_dish_asset = bool(roles & {"menu", "signature_dish", "dish"})
    if not has_dish_asset:
        raise HTTPException(status_code=409, detail="进入确认事实前请先上传菜品或菜单素材")
    use_ai = bool(payload and payload.use_ai)
    task = WorkflowTask(project_id=project_id, task_type="asset_analysis" if use_ai else "dialogue_intake")
    db.add(task)
    db.commit()
    background.add_task(execute_analysis, project.id, task.id, use_ai)
    return {"task_id": task.id, "status": task.status, "use_ai": use_ai}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(WorkflowTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"id": task.id, "project_id": task.project_id, "creation_id": db.scalar(select(CreationConfirmation.creation_id).where(CreationConfirmation.task_id == task.id)), "status": task.status, "progress": task.progress, "result": task.result, "error": {"code": task.error_code, "message": task.error_message} if task.error_code else None}


@router.get("/projects/{project_id}/coverage")
def get_coverage(project_id: str, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    fact = db.scalar(select(FactVersion).where(FactVersion.project_id == project_id, FactVersion.version == project.current_fact_version))
    if fact is None:
        raise HTTPException(status_code=409, detail="项目尚未完成分析")
    return {"fact_version": fact.version, "facts": fact.facts, **coverage_for(fact.facts)}


@router.post("/projects/{project_id}/clarifications")
def submit_clarification(project_id: str, payload: ClarificationSubmit, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    latest = db.scalar(select(FactVersion).where(FactVersion.project_id == project_id).order_by(FactVersion.version.desc()))
    if latest is None:
        raise HTTPException(status_code=409, detail="请先完成素材分析")
    facts = merge_answers(latest.facts, payload.answers)
    new_fact = FactVersion(project_id=project_id, version=latest.version + 1, facts=facts, evidence={**latest.evidence, **{key: {"source": "user_clarification", "confidence": 1.0} for key in payload.answers}})
    db.add(new_fact)
    current_round = db.scalar(select(ClarificationRound).where(ClarificationRound.project_id == project_id).order_by(ClarificationRound.round_index.desc()))
    if current_round:
        current_round.answers = payload.answers
    coverage = coverage_for(facts)
    project.current_fact_version = new_fact.version
    project.status = ProjectStatus.NEEDS_FACT_CONFIRMATION if coverage["ready_for_confirmation"] else ProjectStatus.NEEDS_CLARIFICATION
    if coverage["questions"]:
        next_index = (current_round.round_index + 1) if current_round else 1
        db.add(ClarificationRound(project_id=project_id, round_index=next_index, questions=coverage["questions"]))
    db.commit()
    return {"fact_version": new_fact.version, "facts": facts, "coverage": coverage, "status": project.status}


@router.post("/projects/{project_id}/fact-versions")
def update_facts(project_id: str, payload: FactUpdate, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    latest = db.scalar(select(FactVersion).where(FactVersion.project_id == project_id).order_by(FactVersion.version.desc()))
    facts = payload.model_dump(exclude_none=True)
    if latest:
        facts = {**latest.facts, **facts}
    if payload.store_name is not None:
        candidate_names = {item.get("name") for item in facts.get("detected_store_name_candidates", []) if isinstance(item, dict)}
        if candidate_names and payload.store_name not in candidate_names:
            raise HTTPException(status_code=422, detail="所选门店不在识别候选中")
        facts["detected_store_name_needs_confirmation"] = False
    version = 1 if latest is None else latest.version + 1
    item = FactVersion(project_id=project_id, version=version, facts=facts, evidence={"manual_edit": True})
    db.add(item)
    project.current_fact_version = version
    project.status = ProjectStatus.NEEDS_FACT_CONFIRMATION if coverage_for(facts)["ready_for_confirmation"] else ProjectStatus.NEEDS_CLARIFICATION
    db.commit()
    return {"fact_version": version, "facts": facts, "status": project.status}


@router.post("/projects/{project_id}/fact-versions/{version}/confirm")
def confirm_facts(project_id: str, version: int, payload: FactConfirm, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    fact = db.scalar(select(FactVersion).where(FactVersion.project_id == project_id, FactVersion.version == version))
    if fact is None:
        raise HTTPException(status_code=404, detail="事实版本不存在")
    if version != project.current_fact_version:
        raise HTTPException(status_code=409, detail="只能确认当前最新事实版本")
    coverage = coverage_for(fact.facts)
    if not coverage["ready_for_confirmation"]:
        raise HTTPException(status_code=409, detail="核心信息尚未补齐")
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="必须明确确认后才能锁定事实")
    fact.confirmed_at = utc_now()
    project.status = ProjectStatus.FACTS_CONFIRMED
    db.commit()
    return {"fact_version": version, "confirmed_at": fact.confirmed_at, "status": project.status}


def design_plan_payload(item: DesignPlan) -> dict:
    return {"id": item.id, "project_id": item.project_id, "fact_version": item.fact_version, "version": item.version, "status": item.status, "plan": item.plan, "confirmed_at": item.confirmed_at}


@router.post("/projects/{project_id}/design-plans", status_code=201)
def create_design_plan(project_id: str, payload: DesignPlanCreate | None = None, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    fact = db.scalar(select(FactVersion).where(FactVersion.project_id == project_id, FactVersion.version == project.current_fact_version))
    if fact is None or fact.confirmed_at is None:
        raise HTTPException(status_code=409, detail="请先确认并锁定经营事实")
    latest = db.scalar(select(DesignPlan).where(DesignPlan.project_id == project_id).order_by(DesignPlan.version.desc()))
    if latest and latest.fact_version == fact.version and latest.status == "DRAFT":
        return design_plan_payload(latest)
    style = payload.style if payload else "appetite"
    item = DesignPlan(project_id=project_id, fact_version=fact.version, version=1 if latest is None else latest.version + 1, plan=build_design_plan(fact.facts, style))
    db.add(item)
    project.status = ProjectStatus.DESIGN_PLAN_DRAFT
    db.commit()
    return design_plan_payload(item)


@router.get("/projects/{project_id}/design-plans/latest")
def get_latest_design_plan(project_id: str, db: Session = Depends(get_db)):
    require_project(db, project_id)
    item = db.scalar(select(DesignPlan).where(DesignPlan.project_id == project_id).order_by(DesignPlan.version.desc()))
    if item is None:
        raise HTTPException(status_code=404, detail="设计方案尚未创建")
    return design_plan_payload(item)


@router.patch("/projects/{project_id}/design-plans/{plan_id}")
def patch_design_plan(project_id: str, plan_id: str, payload: DesignPlanUpdate, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    item = db.get(DesignPlan, plan_id)
    if item is None or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="设计方案不存在")
    if item.status != "DRAFT":
        raise HTTPException(status_code=409, detail="已确认方案不能直接修改")
    values = payload.model_dump(exclude_none=True)
    item.plan = update_design_plan(item.plan, **values)
    project.status = ProjectStatus.DESIGN_PLAN_DRAFT
    db.commit()
    return design_plan_payload(item)


@router.post("/projects/{project_id}/design-plans/{plan_id}/confirm")
def confirm_design_plan(project_id: str, plan_id: str, payload: DesignPlanConfirm, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    item = db.get(DesignPlan, plan_id)
    if item is None or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="设计方案不存在")
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="必须明确确认后才能开始生图")
    item.status = "CONFIRMED"
    item.confirmed_at = utc_now()
    project.status = ProjectStatus.DESIGN_PLAN_CONFIRMED
    db.commit()
    return design_plan_payload(item)


def execute_generation(project_id: str, task_id: str, plan_id: str, provider: str, allow_fallback: bool):
    with SessionLocal() as db:
        project = db.get(StoreProject, project_id)
        task = db.get(WorkflowTask, task_id)
        plan = db.get(DesignPlan, plan_id)
        if project and task and plan:
            run_generation(db, project, task, plan, provider, allow_fallback)


@router.post("/projects/{project_id}/generation-runs", status_code=202)
def start_generation(project_id: str, background: BackgroundTasks, payload: GenerationRunRequest, db: Session = Depends(get_db)):
    project = require_project(db, project_id)
    plan = db.scalar(select(DesignPlan).where(DesignPlan.project_id == project_id).order_by(DesignPlan.version.desc()))
    if plan is None or plan.status != "CONFIRMED":
        raise HTTPException(status_code=409, detail="请先确认五图设计方案")
    task = WorkflowTask(project_id=project_id, task_type="group_buying_image_generation")
    db.add(task)
    db.commit()
    background.add_task(execute_generation, project_id, task.id, plan.id, payload.provider, payload.allow_fallback)
    return {"task_id": task.id, "status": task.status, "provider": payload.provider, "allow_fallback": payload.allow_fallback}


@router.post("/tasks/{task_id}/pause")
def pause_generation(task_id: str, db: Session = Depends(get_db)):
    task = db.get(WorkflowTask, task_id)
    if task is None or task.task_type != "group_buying_image_generation":
        raise HTTPException(status_code=404, detail="生图任务不存在")
    if task.status == TaskStatus.SUCCEEDED:
        raise HTTPException(status_code=409, detail="图片已经生成完成，无需暂停")
    if task.status == TaskStatus.FAILED_FINAL:
        raise HTTPException(status_code=409, detail="任务已经失败，可直接重新生成")
    task.status = TaskStatus.NEEDS_USER
    task.error_code = "PAUSED_BY_USER"
    task.error_message = "已暂停；继续生成会重新发起模型调用"
    project = db.get(StoreProject, task.project_id)
    if project:
        project.status = ProjectStatus.DESIGN_PLAN_CONFIRMED
    db.commit()
    return {"id": task.id, "project_id": task.project_id, "status": task.status, "progress": task.progress, "result": task.result, "error": {"code": task.error_code, "message": task.error_message}}


@router.get("/projects/{project_id}/generations/{task_id}/assets/{filename}")
def get_generated_asset(project_id: str, task_id: str, filename: str, db: Session = Depends(get_db)):
    require_project(db, project_id)
    task = db.get(WorkflowTask, task_id)
    if task is None or task.project_id != project_id or task.task_type != "group_buying_image_generation":
        raise HTTPException(status_code=404, detail="生图任务不存在")
    allowed = {task.result.get("long_image"), *(task.result.get("slices") or [])}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="生成图片不存在")
    path = settings.generated_dir / project_id / task_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="生成图片文件不存在")
    return FileResponse(path, media_type="image/png", filename=f"tuanhui-{filename}")
