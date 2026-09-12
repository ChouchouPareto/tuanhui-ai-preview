"""Authoritative stage hooks; success-only rolling estimates, honest cold starts."""
from datetime import timedelta, timezone
from math import ceil
from sqlalchemy import select
from app.models import WorkflowEvent, utc_now


def emit(db, project_id, task_id, stage, state, *, creation_id=None, model="local", duration_ms=None, error_code=None):
    event = WorkflowEvent(project_id=project_id, creation_id=creation_id, task_id=task_id,
                          stage=stage, state=state, model=model,
                          duration_ms=duration_ms, error_code=error_code)
    db.add(event)
    db.commit()
    return event


def iso(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


def estimate(db, stage, model):
    values = db.scalars(select(WorkflowEvent.duration_ms).where(
        WorkflowEvent.stage == stage, WorkflowEvent.model == model,
        WorkflowEvent.state == "completed", WorkflowEvent.duration_ms > 0,
        WorkflowEvent.created_at >= utc_now() - timedelta(days=14),
    ).order_by(WorkflowEvent.created_at.desc()).limit(100)).all()
    if len(values) < 5:
        return {"sample_count": len(values), "range_ms": None}
    values = sorted(values)
    return {"sample_count": len(values), "range_ms": [values[(len(values)-1)//2], values[ceil(len(values)*.9)-1]]}


def activity(db, project_id, *, creation_id=None, task_id=None):
    query = select(WorkflowEvent).where(WorkflowEvent.project_id == project_id)
    if task_id:
        query = query.where(WorkflowEvent.task_id == task_id)
    elif creation_id:
        query = query.where(WorkflowEvent.creation_id == creation_id)
    rows = list(reversed(db.scalars(query.order_by(WorkflowEvent.created_at.desc()).limit(60)).all()))
    spans = {}
    for row in rows:
        key = (row.task_id, row.stage)
        if row.state == "started":
            spans[key] = {"stage": row.stage, "task_id": row.task_id, "started_at": iso(row.created_at),
                          "state": "running", "model": row.model, "duration_ms": None}
        elif key in spans:
            spans[key].update(state=row.state, duration_ms=row.duration_ms, finished_at=iso(row.created_at), error_code=row.error_code)
    current = spans.get((rows[-1].task_id, rows[-1].stage)) if rows else None
    if current:
        current["estimate"] = estimate(db, current["stage"], current["model"])
    return {"server_time": iso(utc_now()), "current": current, "spans": list(spans.values())}
