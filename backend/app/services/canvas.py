"""Immutable native objects, conservative target resolution and local-only edits."""
import hashlib
import io
import json
import re
import time
from pathlib import Path

from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.canvas_schemas import Scene, Operation, MutateCanvas
from app.core.config import settings
from app.models import (CanvasDocument, CanvasVersion, CanvasMutation, CanvasProposal,
                        StoreProject, ProjectDisplayState, WorkflowTask, TaskStatus,
                        WorkflowEvent, new_id)
from app.services.canvas_render import render_scene
from app.services.intake import fail, digest, selected_assets
from app.services.master_layout import eligible_dishes, add_export_watermark


def require_project(db, project_id):
    project = db.get(StoreProject, project_id)
    state = db.get(ProjectDisplayState, project_id)
    if not project or (state and state.visibility == "deleted"):
        fail("NOT_FOUND", "项目不存在或已删除", 404)
    return project


def document(db, project_id, document_id):
    require_project(db, project_id)
    doc = db.get(CanvasDocument, document_id)
    if not doc or doc.project_id != project_id:
        fail("NOT_FOUND", "画布不属于当前项目", 404)
    return doc


def version(db, doc, version_id):
    ver = db.get(CanvasVersion, version_id)
    if not ver or ver.document_id != doc.id:
        fail("NOT_FOUND", "作品版本不存在", 404)
    if digest(ver.content) != ver.content_hash:
        fail("VERSION_INTEGRITY_FAILED", "版本内容校验失败，未继续修改")
    return ver


def view(doc, ver):
    return {"document_id": doc.id, "project_id": doc.project_id, "name": doc.name,
            "head_version_id": doc.head_version_id, "version_id": ver.id,
            "parent_version_id": ver.parent_id, "reason": ver.reason,
            "scene": ver.content, "content_hash": ver.content_hash,
            "render_contract": ver.render_manifest.get("contract"),
            "text_layout": ver.render_manifest.get("text_layout", []),
            "source_task_id": doc.source.get("task_id"),
            "visual_editability": "flattened_underlay" if doc.source else "native_objects",
            "image_model_calls": 0}


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_dir(project_id, task_id):
    root = settings.generated_dir.resolve()
    path = (root / project_id / task_id).resolve()
    if not path.is_relative_to(root):
        fail("INVALID_SOURCE", "来源路径不合法", 422)
    return path


def underlay(doc):
    if not doc.source:
        return None
    path = source_dir(doc.project_id, doc.source["task_id"]) / "typography-base.png"
    if not path.is_file() or file_hash(path) != doc.source["underlay_sha256"]:
        fail("SOURCE_CHANGED", "原始无字底层缺失或发生变化；未重生成")
    with Image.open(path) as image:
        return image.convert("RGB")


def check_scene(db, doc, scene):
    from app.services.image_generation import _font
    ids = [n.asset_id for n in scene.nodes if n.kind == "image"]
    assets = selected_assets(db, doc.project_id, ids)
    permitted = eligible_dishes(assets)
    if len(permitted) != len(assets):
        fail("ASSET_ROLE_FORBIDDEN", "门头、菜单及未确认用途素材不能放入成品", 422)
    if doc.source and scene.ai_generated != doc.source["ai_generated"]:
        fail("SOURCE_FLAG_IMMUTABLE", "来源标识不能通过编辑对象删除", 422)
    try:
        return render_scene(scene, _font, underlay(doc), {a.id: a for a in assets})
    except ValueError as exc:
        fail("SCENE_VALIDATION_FAILED", str(exc), 422)
    except OSError:
        fail("ASSET_UNREADABLE", "作品素材暂时无法读取；未重新生成", 422)


def artifact_dir(doc, ver):
    root = settings.generated_dir.resolve()
    path = (root / doc.project_id / "canvas_versions" / doc.id / ver.id).resolve()
    if not path.is_relative_to(root):
        fail("INVALID_SOURCE", "作品存储位置不合法", 422)
    return path


def save_render(doc, ver, scene, image, text_layout):
    """Freeze actual pixels with each version, so later font/code changes cannot
    change already delivered work. Uncommitted UUID directories aren't exposed.
    Files use exclusive creation; no user artifact is ever overwritten.
    """
    from app.services.image_generation import _font
    folder = artifact_dir(doc, ver)
    try:
        folder.mkdir(parents=True, exist_ok=False)
        marked = add_export_watermark(image, scene.slice_count, _font) if scene.ai_generated else image
        hashes = {}
        for name, canvas in (("clean.png", image), ("marked.png", marked)):
            buf = io.BytesIO()
            canvas.save(buf, format="PNG")
            raw = buf.getvalue()
            with (folder / name).open("xb") as stream:
                stream.write(raw)
            hashes[name] = hashlib.sha256(raw).hexdigest()
        ver.render_manifest = {"contract": "native-render-v1", "hashes": hashes, "text_layout": text_layout}
    except OSError:
        fail("VERSION_SAVE_FAILED", "新版本文件未能保存，旧作品没有改变；请检查存储后再试", 503)


def create(db, project_id, name, scene, source=None):
    require_project(db, project_id)
    started = time.monotonic()
    doc = CanvasDocument(id=new_id(), project_id=project_id, name=name, source=source or {})
    image, layout = check_scene(db, doc, scene)
    ver = CanvasVersion(id=new_id(), document_id=doc.id, content=scene.model_dump(mode="json"),
                        reason="import" if source else "create", parent_id=None)
    ver.content_hash = digest(ver.content)
    save_render(doc, ver, scene, image, layout)
    doc.head_version_id = ver.id
    db.add(doc)
    db.flush()
    db.add(ver)
    db.add(WorkflowEvent(project_id=project_id, task_id=doc.id, stage="canvas_create", state="completed",
                         duration_ms=max(1, int((time.monotonic()-started)*1000))))
    db.commit()
    return view(doc, ver)


def import_task(db, project_id, task_id, deliverable_id=None):
    require_project(db, project_id)
    task = db.get(WorkflowTask, task_id)
    if not task or task.project_id != project_id:
        fail("NOT_FOUND", "作品不存在", 404)
    if task.status != TaskStatus.SUCCEEDED:
        fail("SOURCE_NOT_READY", "只能编辑已完成的作品")
    # Bundles contain child task IDs, not arbitrary file paths. The caller must
    # choose the child work; never guess the first item of a full-plan package.
    if (task.result or {}).get("deliverables") or deliverable_id:
        fail("CHILD_WORK_REQUIRED", "请传入要修改的单项作品任务 ID", 422)
    folder = source_dir(project_id, task.id)
    manifest, base = folder / "editable-scene.json", folder / "typography-base.png"
    if not manifest.is_file() or not base.is_file():
        fail("NO_EDITABLE_SOURCE", "此历史作品没有原生文字层，不能保证只改标题；未调用模型")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        scene = Scene.model_validate(data["scene"])
        if file_hash(base) != data["underlay_sha256"]:
            raise ValueError("底图校验失败")
    except (KeyError, ValueError, OSError):
        fail("INVALID_SOURCE", "原生作品结构或底图校验失败，未调用模型", 422)
    return create(db, project_id, "作品编辑", scene, {"task_id": task.id,
                  "underlay_sha256": data["underlay_sha256"], "ai_generated": scene.ai_generated})


def mutation_replay(db, doc, key, request_hash):
    row = db.scalar(select(CanvasMutation).where(CanvasMutation.document_id == doc.id, CanvasMutation.request_key == key))
    if row:
        if row.request_hash != request_hash:
            fail("IDEMPOTENCY_CONFLICT", "同一个提交标识不能用于不同修改")
        db.refresh(doc)
        return view(doc, version(db, doc, row.version_id))
    return None


def append_version(db, doc, base_id, key, request_hash, scene, reason, proposal=None):
    started = time.monotonic()
    repeated = mutation_replay(db, doc, key, request_hash)
    if repeated:
        return repeated
    if doc.head_version_id != base_id:
        fail("STALE_VERSION", "作品已有新版本，请先查看新版本；原版本仍保留")
    image, layout = check_scene(db, doc, scene)
    ver = CanvasVersion(id=new_id(), document_id=doc.id, parent_id=base_id,
                        content=scene.model_dump(mode="json"), reason=reason)
    ver.content_hash = digest(ver.content)
    # Compare-and-swap protects two tabs/workers editing the same head. The new
    # version, event and idempotency receipt are committed in the same transaction.
    claimed = db.execute(update(CanvasDocument).where(CanvasDocument.id == doc.id,
        CanvasDocument.head_version_id == base_id).values(head_version_id=ver.id).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        db.refresh(doc)
        repeated = mutation_replay(db, doc, key, request_hash)
        if repeated:
            return repeated
        fail("STALE_VERSION", "另一项修改已保存，请先查看新版本")
    save_render(doc, ver, scene, image, layout)
    db.add(ver)
    db.flush()
    db.add(CanvasMutation(document_id=doc.id, request_key=key, request_hash=request_hash, version_id=ver.id))
    if proposal:
        proposal.applied_version_id = ver.id
    db.add(WorkflowEvent(project_id=doc.project_id, task_id=doc.id, stage="canvas_edit", state="completed",
                         duration_ms=max(1, int((time.monotonic()-started)*1000))))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.refresh(doc)
        repeated = mutation_replay(db, doc, key, request_hash)
        if repeated:
            return repeated
        fail("EDIT_CONFLICT", "修改发生冲突，请重新查看作品")
    db.refresh(doc)
    return view(doc, ver)


def mutated_scene(scene, operations):
    nodes = {n.id: n.model_dump(mode="json") for n in scene.nodes}
    for operation in operations:
        node = nodes.get(operation.object_id)
        if operation.op == "add":
            if node:
                fail("OBJECT_EXISTS", "该对象 ID 已存在", 422)
            nodes[operation.object_id] = operation.node.model_dump(mode="json")
            continue
        if not node:
            fail("OBJECT_NOT_FOUND", "指定对象不存在", 422)
        if node["locked"] and operation.op != "unlock":
            fail("OBJECT_LOCKED", "这个对象已锁定，请先明确解锁")
        if operation.op == "remove":
            del nodes[operation.object_id]
        elif operation.op in {"lock", "unlock"}:
            node["locked"] = operation.op == "lock"
        else:
            node.update(operation.patch.model_dump(exclude_none=True))
    try:
        return Scene.model_validate({**scene.model_dump(mode="json"), "nodes": list(nodes.values())})
    except ValidationError as exc:
        fail("INVALID_EDIT", str(exc), 422)


def mutate(db, doc, payload):
    request_hash = digest({"action": "mutate", **payload.model_dump(mode="json")})
    repeated = mutation_replay(db, doc, payload.request_key, request_hash)
    if repeated:
        return repeated
    ver = version(db, doc, payload.base_version_id)
    scene = mutated_scene(Scene.model_validate(ver.content), payload.operations)
    return append_version(db, doc, ver.id, payload.request_key, request_hash, scene, "edit")


def restore(db, doc, payload):
    target = version(db, doc, payload.target_version_id)
    version(db, doc, payload.base_version_id)
    return append_version(db, doc, payload.base_version_id, payload.request_key,
                          digest({"action": "restore", **payload.model_dump(mode="json")}),
                          Scene.model_validate(target.content), "restore")


def resolve_edit(db, doc, payload):
    started = time.monotonic()
    ver = version(db, doc, payload.version_id)
    if ver.id != doc.head_version_id:
        fail("STALE_VERSION", "请先切换到最新版本，或明确复制此历史版本后编辑")
    scene = Scene.model_validate(ver.content)
    all_text = [n for n in scene.nodes if n.kind == "text" and n.visible]
    candidates = list(all_text)
    constraints = []
    if payload.selected_object_id:
        constraints.append({payload.selected_object_id})
    if payload.quote:
        constraints.append({n.id for n in all_text if n.text == payload.quote})
    if payload.role:
        constraints.append({n.id for n in all_text if n.role == payload.role})
    if payload.slice_index:
        if payload.slice_index > scene.slice_count:
            fail("INVALID_SLICE", "该作品没有这一张切片", 422)
        constraints.append({n.id for n in all_text if int((n.box[0]+n.box[2]/2)*scene.slice_count)+1 == payload.slice_index})
    # Extract only explicit locators. A model's confidence never authorizes a write.
    for word, role in (("主标题", "headline"), ("副标题", "subheadline"), ("店名", "store_name"), ("价格", "price")):
        if word in payload.message:
            constraints.append({n.id for n in all_text if n.role == role})
    quoted = re.findall(r'[“「『"]([^”」』"]+)[”」』"]', payload.message)
    if quoted and re.search(r"[”」』\"]\s*(?:改成|改为|换成|替换为)", payload.message):
        constraints.append({n.id for n in all_text if n.text == quoted[0]})
    if "标题" in payload.message and "主标题" not in payload.message and "副标题" not in payload.message:
        constraints.append({n.id for n in all_text if n.role in {"headline", "subheadline"}})
    if constraints:
        candidates = [n for n in all_text if all(n.id in ids for ids in constraints)]
    replacement = payload.replacement
    if replacement is None:
        match = re.search(r"(?:改成|改为|换成|替换为)\s*[：:]?\s*(.+?)\s*$", payload.message)
        if match:
            replacement = match.group(1).strip().strip('“”「」『』"')
    # Compound/local visual requests are not silently reduced to one text edit.
    compound = bool(re.search(r"同时|并且|另外|顺便|背景|重新生成|整张|全部|颜色|字体|字号|放大|缩小|移动|加粗|居中|位置", payload.message))
    prefix = re.split(r"改成|改为|换成|替换为", payload.message, maxsplit=1)[0]
    compound = compound or bool(re.search(r"不要|不想|别|先不|不需要|不准|能不能|可不可以|是否|请问|会不会", prefix))
    status = "ready"
    if not constraints or len(candidates) != 1:
        status = "needs_target" if candidates or not constraints else "target_conflict"
    elif candidates[0].locked:
        status = "object_locked"
    elif replacement is None or compound:
        status = "needs_action"
    result = {"status": status, "version_id": ver.id, "can_apply": False, "image_model_calls": 0,
              "candidates": [{"object_id": n.id, "role": n.role, "text": n.text, "box": list(n.box)}
                             for n in (candidates if candidates else all_text)],
              "message": {"needs_target": "你想改哪一句？点选图片上的文字，或选下面的原文就行。",
                          "target_conflict": "选中的位置和文字描述不是同一个对象，你想改哪一个？",
                          "object_locked": "这段文字已锁定，先解锁后才能修改。",
                          "needs_action": "这次先改哪一项、改成什么？我会保留其他内容。",
                          "ready": "已定位这段文字，只修改文字层，其他对象保持不变。"}[status]}
    if status == "ready":
        op = Operation.model_validate({"op": "update", "object_id": candidates[0].id, "patch": {"text": replacement}})
        edited = mutated_scene(scene, [op])
        check_scene(db, doc, edited)
        proposal = CanvasProposal(document_id=doc.id, base_version_id=ver.id,
                                  proposal={"operations": [op.model_dump(mode="json", exclude_none=True)]})
        db.add(proposal)
        db.flush()
        result.update(proposal_id=proposal.id, can_apply=True, before=candidates[0].text, after=replacement)
    db.add(WorkflowEvent(project_id=doc.project_id, task_id=doc.id, stage="edit_resolve", state=status,
                         duration_ms=max(1, int((time.monotonic()-started)*1000))))
    db.commit()
    return result


def apply_proposal(db, doc, proposal_id, payload):
    proposal = db.get(CanvasProposal, proposal_id)
    if not proposal or proposal.document_id != doc.id:
        fail("NOT_FOUND", "修改方案不存在", 404)
    if proposal.base_version_id != payload.base_version_id:
        fail("PROPOSAL_VERSION_CONFLICT", "修改方案不属于指定版本")
    request_hash = digest({"action": "proposal", "proposal_id": proposal.id, **payload.model_dump(mode="json")})
    repeated = mutation_replay(db, doc, payload.request_key, request_hash)
    if repeated:
        return repeated
    if proposal.applied_version_id:
        # A proposal can only be applied once even with a new network request key.
        return view(doc, version(db, doc, proposal.applied_version_id))
    ver = version(db, doc, proposal.base_version_id)
    operations = [Operation.model_validate(o) for o in proposal.proposal["operations"]]
    scene = mutated_scene(Scene.model_validate(ver.content), operations)
    return append_version(db, doc, ver.id, payload.request_key, request_hash, scene, "targeted_text_edit", proposal)


def export_images(db, doc, ver, watermark=True):
    started = time.monotonic()
    scene = Scene.model_validate(ver.content)
    name = "marked.png" if watermark else "clean.png"
    path = artifact_dir(doc, ver) / name
    try:
        if not path.is_file() or file_hash(path) != ver.render_manifest.get("hashes", {}).get(name):
            fail("VERSION_ARTIFACT_CHANGED", "这版图片缺失或校验失败，未自动重画")
        with Image.open(path) as image:
            canvas = image.convert("RGB")
        if canvas.size != (scene.width, scene.height):
            fail("VERSION_ARTIFACT_CHANGED", "这版图片尺寸与版本不一致")
    except OSError:
        fail("VERSION_ARTIFACT_UNREADABLE", "这版图片暂时无法读取，未自动重画")
    # Bytes are returned to the response or ZIP writer, never to the model.
    result = {"long.png": canvas}
    for index in range(scene.slice_count):
        result[f"{index+1:02d}.png"] = canvas.crop((index*800, 0, (index+1)*800, 600))
    db.add(WorkflowEvent(project_id=doc.project_id, task_id=doc.id, stage="canvas_export", state="completed",
                         duration_ms=max(1, int((time.monotonic()-started)*1000))))
    db.commit()
    return result, ver.render_manifest.get("text_layout", [])
