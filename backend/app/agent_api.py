"""Local workbench API. Explicit authorization separates planning from generation."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.config import settings
from app.core.admin_access import require_admin
from app.agent_schemas import AgentInput, AgentExecute, WorkspaceUpdate, ReviewTemplate
from app.models import AgentRun, WorkflowTask, TaskStatus, WorkspaceState, TemplateReview
from app.services import agent_runtime as runtime, canvas
from app.services.intake import fail, digest, ConfirmInput

router = APIRouter(prefix="/api/v1", tags=["bounded workbench"])


@router.get("/agent/contracts", dependencies=[Depends(require_admin)])
def contracts():
    return {"version":"bounded-agent-v1", "provider":"bailian", "text_model":settings.bailian_text_model,
            "vision_model":settings.bailian_vision_model, "image_model":settings.qwen_image_model,
            "credential_configured":bool(settings.dashscope_api_key), "max_text_calls":settings.agent_max_text_calls,
            "automatic_retry":False, "generation_requires_confirmation":True, "deployment":"local-single-user"}


@router.post("/projects/{project_id}/agent-runs")
def submit(project_id: str, payload: AgentInput, db: Session = Depends(get_db)):
    return runtime.submit(db, project_id, payload)


@router.get("/projects/{project_id}/agent-runs")
def history(project_id: str, db: Session = Depends(get_db)):
    canvas.require_project(db, project_id)
    rows = db.scalars(select(AgentRun).where(AgentRun.project_id == project_id).order_by(AgentRun.created_at.desc()).limit(100)).all()
    return [runtime.view(db, row) for row in rows]


@router.get("/projects/{project_id}/agent-runs/{run_id}")
def get_run(project_id: str, run_id: str, db: Session = Depends(get_db)):
    return runtime.view(db, runtime.require_run(db, project_id, run_id))


@router.post("/projects/{project_id}/agent-runs/{run_id}/cancel")
def cancel(project_id: str, run_id: str, db: Session = Depends(get_db)):
    run = runtime.require_run(db, project_id, run_id)
    changed = db.execute(update(AgentRun).where(AgentRun.id == run.id, AgentRun.state.in_(["QUEUED", "RUNNING"]))
                         .values(state="CANCELLED", lease_until=None))
    if changed.rowcount:
        db.execute(update(WorkflowTask).where(WorkflowTask.id == run.task_id).values(status=TaskStatus.NEEDS_USER,
            error_code="USER_CANCELLED", error_message="已停止后续工作；已发出的模型请求可能仍计费。"))
    db.commit()
    if changed.rowcount:
        from app.services.telemetry import emit
        emit(db, project_id, run.task_id, "agent_workflow", "cancelled", error_code="USER_CANCELLED")
    return runtime.view(db, run)


@router.post("/projects/{project_id}/agent-runs/{run_id}/execute")
def execute(project_id: str, run_id: str, payload: AgentExecute, db: Session = Depends(get_db)):
    run = runtime.require_run(db, project_id, run_id)
    review = run.result.get("review")
    if run.state != "SUCCEEDED" or run.result.get("kind") != "review" or not review:
        fail("NO_EXECUTABLE_PLAN", "这条对话没有可以生成的方案")
    if payload.snapshot_hash != review["snapshot_hash"]:
        fail("STALE_REVISION", "确认内容已变化，请重新检查")
    from app.creation_api import confirm
    return confirm(project_id, review["creation_id"], ConfirmInput(expected_revision=review["revision"],
        snapshot_hash=payload.snapshot_hash, approved_image_calls=payload.approved_image_calls,
        materials_confirmed=payload.materials_confirmed, accepted_budget_policy=payload.accepted_policy),
        f"agent_execute_{run.id}", db)


@router.get("/projects/{project_id}/editor-workspace")
def workspace(project_id: str, db: Session = Depends(get_db)):
    canvas.require_project(db, project_id)
    row = db.get(WorkspaceState, project_id)
    return {"revision":row.revision, **row.content} if row else {"revision":0, "positions":{}, "viewport":[0,0,1]}


@router.patch("/projects/{project_id}/editor-workspace")
def save_workspace(project_id: str, payload: WorkspaceUpdate, db: Session = Depends(get_db)):
    canvas.require_project(db, project_id)
    for document_id in payload.positions:
        canvas.document(db, project_id, document_id)
    content = payload.model_dump(exclude={"expected_revision"})
    row = db.get(WorkspaceState, project_id)
    if row:
        changed = db.execute(update(WorkspaceState).where(WorkspaceState.project_id == project_id,
            WorkspaceState.revision == payload.expected_revision).values(revision=payload.expected_revision+1, content=content))
        if not changed.rowcount:
            fail("STALE_REVISION", "画布布局已更新，请重新载入")
    elif payload.expected_revision != 0:
        fail("STALE_REVISION", "画布布局版本不存在")
    else:
        db.add(WorkspaceState(project_id=project_id, revision=1, content=content))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("STALE_REVISION", "其他窗口已保存布局，请重新载入")
    return workspace(project_id, db)


@router.get("/templates/reviews", dependencies=[Depends(require_admin)])
def templates(db: Session = Depends(get_db)):
    from app.services.layout_catalog import ALL_LAYOUTS, catalog_entry
    result = []
    for template in ALL_LAYOUTS:
        value = catalog_entry(template)
        fingerprint = digest(value)
        row = db.get(TemplateReview, value["id"])
        result.append({**value, "template_hash":fingerprint,
            "review_state":row.state if row and row.template_hash == fingerprint else "draft",
            "notes":row.notes if row else ""})
    return result


@router.post("/templates/{template_id}/review", dependencies=[Depends(require_admin)])
def review_template(template_id: str, payload: ReviewTemplate, db: Session = Depends(get_db)):
    value = next((t for t in templates(db) if t["id"] == template_id), None)
    if not value:
        fail("NOT_FOUND", "模板不存在", 404)
    if value["template_hash"] != payload.template_hash:
        fail("STALE_TEMPLATE", "模板内容已变化，需要重新审核")
    from app.models import utc_now
    db.merge(TemplateReview(template_id=template_id, template_hash=payload.template_hash,
        state=payload.state, notes=payload.notes, reviewed_at=utc_now()))
    db.commit()
    return {"template_id":template_id, **payload.model_dump()}
