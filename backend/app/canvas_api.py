"""Backend-only editor contract. Frontend/Figma integration is a separate phase."""
import io
import time
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.canvas_schemas import (CreateCanvas, ImportCanvas, MutateCanvas, RestoreCanvas,
                                ResolveEdit, ApplyProposal)
from app.core.database import get_db
from app.models import CanvasDocument, CanvasVersion, WorkflowEvent
from app.services import canvas
from app.services.intake import fail

router = APIRouter(prefix="/api/v1/projects/{project_id}/canvases", tags=["native editable objects"])


def observed(db, doc, stage, action, *args):
    started = time.monotonic()
    project_id, document_id = doc.project_id, doc.id
    try:
        return action(db, doc, *args)
    except HTTPException as error:
        # Roll back a failed mutation before recording rejection. No raw user
        # text, file path or provider credential enters these hooks.
        db.rollback()
        code = error.detail.get("code", "REQUEST_REJECTED") if isinstance(error.detail, dict) else "REQUEST_REJECTED"
        db.add(WorkflowEvent(project_id=project_id, task_id=document_id, stage=stage, state="failed",
                             error_code=code, duration_ms=max(1, int((time.monotonic()-started)*1000))))
        db.commit()
        raise


@router.post("")
def create(project_id: str, payload: CreateCanvas, db: Session = Depends(get_db)):
    return canvas.create(db, project_id, payload.name, payload.scene)


@router.post("/import")
def import_work(project_id: str, payload: ImportCanvas, db: Session = Depends(get_db)):
    return canvas.import_task(db, project_id, payload.task_id, payload.deliverable_id)


@router.get("")
def list_canvases(project_id: str, db: Session = Depends(get_db)):
    canvas.require_project(db, project_id)
    docs = db.scalars(select(CanvasDocument).where(CanvasDocument.project_id == project_id)
                      .order_by(CanvasDocument.created_at.desc(), CanvasDocument.id).limit(100)).all()
    return [{"document_id": d.id, "name": d.name, "head_version_id": d.head_version_id} for d in docs]


@router.get("/{document_id}")
def get_canvas(project_id: str, document_id: str, db: Session = Depends(get_db)):
    doc = canvas.document(db, project_id, document_id)
    return canvas.view(doc, canvas.version(db, doc, doc.head_version_id))


@router.get("/{document_id}/versions")
def versions(project_id: str, document_id: str, db: Session = Depends(get_db)):
    doc = canvas.document(db, project_id, document_id)
    rows = db.scalars(select(CanvasVersion).where(CanvasVersion.document_id == doc.id)
                      .order_by(CanvasVersion.created_at.desc(), CanvasVersion.id).limit(100)).all()
    return [{"version_id": v.id, "parent_version_id": v.parent_id, "reason": v.reason,
             "content_hash": v.content_hash, "created_at": v.created_at} for v in rows]


@router.get("/{document_id}/versions/{version_id}")
def get_version(project_id: str, document_id: str, version_id: str, db: Session = Depends(get_db)):
    doc = canvas.document(db, project_id, document_id)
    return canvas.view(doc, canvas.version(db, doc, version_id))


@router.post("/{document_id}/mutations")
def mutate(project_id: str, document_id: str, payload: MutateCanvas, db: Session = Depends(get_db)):
    return observed(db, canvas.document(db, project_id, document_id), "canvas_edit", canvas.mutate, payload)


@router.post("/{document_id}/restore")
def restore(project_id: str, document_id: str, payload: RestoreCanvas, db: Session = Depends(get_db)):
    return observed(db, canvas.document(db, project_id, document_id), "canvas_edit", canvas.restore, payload)


@router.post("/{document_id}/versions/{version_id}/fork")
def fork(project_id: str, document_id: str, version_id: str, db: Session = Depends(get_db)):
    from app.canvas_schemas import Scene
    doc = canvas.document(db, project_id, document_id)
    ver = canvas.version(db, doc, version_id)
    return canvas.create(db, project_id, f"{doc.name[:110]} · 副本", Scene.model_validate(ver.content), doc.source)


@router.post("/{document_id}/resolve-edit")
def resolve(project_id: str, document_id: str, payload: ResolveEdit, db: Session = Depends(get_db)):
    return observed(db, canvas.document(db, project_id, document_id), "edit_resolve", canvas.resolve_edit, payload)


@router.post("/{document_id}/proposals/{proposal_id}/apply")
def apply(project_id: str, document_id: str, proposal_id: str, payload: ApplyProposal, db: Session = Depends(get_db)):
    return observed(db, canvas.document(db, project_id, document_id), "canvas_edit", canvas.apply_proposal, proposal_id, payload)


@router.get("/{document_id}/versions/{version_id}/assets/{filename}")
def preview(project_id: str, document_id: str, version_id: str, filename: str,
            watermark: bool = True, download: bool = False, db: Session = Depends(get_db)):
    doc = canvas.document(db, project_id, document_id)
    ver = canvas.version(db, doc, version_id)
    valid_names = {"long.png", *[f"{i+1:02d}.png" for i in range(ver.content["slice_count"])]}
    if filename not in valid_names:
        fail("NOT_FOUND", "图片不存在", 404)
    images, _ = canvas.export_images(db, doc, ver, watermark)
    output = io.BytesIO()
    images[filename].save(output, format="PNG")
    disposition = "attachment" if download else "inline"
    return Response(output.getvalue(), media_type="image/png",
                    headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                             "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{document_id}/versions/{version_id}/export")
def export(project_id: str, document_id: str, version_id: str, watermark: bool = Query(True), db: Session = Depends(get_db)):
    doc = canvas.document(db, project_id, document_id)
    ver = canvas.version(db, doc, version_id)
    images, _ = canvas.export_images(db, doc, ver, watermark)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, image in images.items():
            png = io.BytesIO()
            image.save(png, format="PNG")
            archive.writestr(name, png.getvalue())
    return Response(output.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="artwork.zip"'})
