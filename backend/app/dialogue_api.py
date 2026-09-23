import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import DialogueTurn, StoreProject
from app.services.intake import fail
from app.services.dialogue_routing import resolve_target, route_reply

router = APIRouter(prefix="/api/v1/dialogue", tags=["dialogue safety"])


class RouteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(default="", max_length=8000)
    project_id: str | None = Field(default=None, max_length=36)
    creation_id: str | None = Field(default=None, max_length=36)
    task_id: str | None = Field(default=None, max_length=36)
    new_session: bool = False


@router.post("/route")
def route(payload: RouteInput, db: Session = Depends(get_db)):
    started = time.monotonic()
    if not payload.project_id and (payload.creation_id or payload.task_id):
        fail("PROJECT_REQUIRED", "请先打开这版作品所属项目。", 422)
    if payload.project_id and not db.get(StoreProject, payload.project_id):
        fail("NOT_FOUND", "项目不存在", 404)
    if payload.new_session and (payload.creation_id or payload.task_id):
        fail("TARGET_CONFLICT", "新建创作不能同时指定历史作品。", 422)
    task, ambiguous = resolve_target(db, payload.project_id, payload.creation_id, payload.task_id) if payload.project_id and not payload.new_session else (None, False)
    result = route_reply(db, payload.text, task, ambiguous)
    result["duration_ms"] = max(1, int((time.monotonic() - started) * 1000))
    # Separate transcript: never edit intake facts, successful artifacts or task state.
    if payload.project_id and not result["can_prepare"]:
        db.add(DialogueTurn(project_id=payload.project_id, creation_id=payload.creation_id,
            task_id=task.id if task else None, text=payload.text, response=result))
        db.commit()
    return result


@router.get("/history")
def history(project_id: str, creation_id: str | None = None, task_id: str | None = None, db: Session = Depends(get_db)):
    if not db.get(StoreProject, project_id):
        fail("NOT_FOUND", "项目不存在", 404)
    task, _ = resolve_target(db, project_id, creation_id, task_id)
    query = select(DialogueTurn).where(DialogueTurn.project_id == project_id)
    if task:
        query = query.where(DialogueTurn.task_id == task.id)
    elif creation_id:
        query = query.where(DialogueTurn.creation_id == creation_id)
    else:
        query = query.where(DialogueTurn.task_id.is_(None), DialogueTurn.creation_id.is_(None))
    rows = db.scalars(query.order_by(DialogueTurn.created_at.desc(), DialogueTurn.id.desc()).limit(30)).all()
    return [{"id": row.id, "text": row.text, "response": row.response} for row in reversed(rows)]
