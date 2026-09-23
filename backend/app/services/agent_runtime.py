"""Persisted parent/child tasks. No arbitrary tools, recursive agents or paid retry."""
import json
import time
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from app.agent_schemas import AgentInput, AgentDecision
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AgentRun, WorkflowTask, TaskStatus, ModelCallRecord, ModelUsageRecord, utc_now
from app.services import canvas, model_gateway
from app.services.intake import digest, fail, selected_assets, LABELS
from app.services.telemetry import emit


def require_run(db, project_id, run_id):
    canvas.require_project(db, project_id)
    run = db.get(AgentRun, run_id)
    if not run or run.project_id != project_id:
        fail("NOT_FOUND", "对话任务不存在", 404)
    return run


def view(db, run):
    task = db.get(WorkflowTask, run.task_id)
    from app.models import CreationConfirmation
    review = run.result.get("review") or {}
    generation = db.scalar(select(CreationConfirmation).where(CreationConfirmation.creation_id == review.get("creation_id"),
        CreationConfirmation.revision == review.get("revision"))) if review else None
    return {"id": run.id, "project_id": run.project_id, "task_id": run.task_id,
            "generation_task_id": generation.task_id if generation else None,
            "state": run.state, "entry_mode": run.request["entry_mode"], "text": run.request["text"],
            "result": run.result, "error": task.error_message, "created_at": run.created_at,
            "text_calls": db.scalar(select(func.count(ModelCallRecord.id)).where(ModelCallRecord.task_id == run.task_id))}


def submit(db, project_id, payload):
    canvas.require_project(db, project_id)
    previous = db.scalar(select(AgentRun).where(AgentRun.project_id == project_id, AgentRun.request_key == payload.request_key))
    fingerprint = digest(payload.model_dump())
    if previous:
        if previous.request_hash != fingerprint:
            fail("IDEMPOTENCY_CONFLICT", "请求标识已用于其他内容")
        return view(db, previous)
    selected_assets(db, project_id, payload.asset_ids)
    if payload.task_id:
        task = db.get(WorkflowTask, payload.task_id)
        if not task or task.project_id != project_id:
            fail("NOT_FOUND", "目标作品不属于当前项目", 404)
    if payload.document_id:
        doc = canvas.document(db, project_id, payload.document_id)
        canvas.version(db, doc, payload.version_id)
    if payload.approved_text_calls > settings.agent_max_text_calls:
        fail("BUDGET_LIMIT", "超过服务端允许的单次语言调用上限")
    from app.services.worker_status import worker_available
    if not worker_available(db):
        fail("WORKER_UNAVAILABLE", "执行器尚未就绪，没有调用模型", 503)
    run_id = str(uuid5(NAMESPACE_URL, f"agent-v1:{project_id}:{payload.request_key}"))
    task = WorkflowTask(id=run_id, project_id=project_id, task_type="agent_orchestration")
    run = AgentRun(id=run_id, task_id=run_id, project_id=project_id, request_key=payload.request_key,
                   request_hash=fingerprint, request=payload.model_dump(), result={})
    db.add_all([task, run])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return submit(db, project_id, payload)
    emit(db, project_id, run_id, "agent_queue", "started")
    return view(db, run)


def active(db, run):
    db.refresh(run)
    if run.state != "RUNNING":
        fail("AGENT_STOPPED", "任务已停止，未继续后续操作")


def call_role(db, run, role, system, context):
    active(db, run)
    calls = db.scalars(select(ModelCallRecord).where(ModelCallRecord.task_id == run.task_id)).all()
    if len(calls) >= run.request["approved_text_calls"]:
        fail("TEXT_BUDGET_EXHAUSTED", "语言调用预算已用完；没有重试")
    record = ModelCallRecord(project_id=run.project_id, task_id=run.task_id, provider="bailian",
        model=settings.bailian_text_model, contract=f"agent-{role}-v1", status="RUNNING")
    db.add(record)
    db.commit()  # reserve before external effects; unknown calls still consume budget
    emit(db, run.project_id, run.id, role, "started", model=record.model)
    started = time.monotonic()
    prompt = json.dumps(context, ensure_ascii=False)
    try:
        raw, usage, duration = model_gateway._post_chat(record.model, [
            {"role": "system", "content": system}, {"role": "user", "content": prompt}])
        record.duration_ms = duration
        record.input_tokens = usage.get("prompt_tokens")
        record.output_tokens = usage.get("completion_tokens")
        db.add(ModelUsageRecord(call_id=record.id, usage=usage, request_ms=duration,
            prompt_characters=len(prompt)+len(system), prompt_sha256=digest([system,prompt]),
            request_options={"role": role, "enable_thinking": False, "response_format": "json_object"}))
        db.commit()
        value = model_gateway.parse_json_object(raw)
        record.status = "SUCCEEDED"
        db.commit()
        emit(db, run.project_id, run.id, role, "completed", model=record.model, duration_ms=duration)
    except Exception as exc:
        record.status = "UNKNOWN" if getattr(exc, "code", "") == "MODEL_TIMEOUT" else "FAILED"
        record.error_code = getattr(exc, "code", "AGENT_OUTPUT_REJECTED")
        record.duration_ms = max(1, int((time.monotonic()-started)*1000))
        db.commit()
        emit(db, run.project_id, run.id, role, "failed", model=record.model,
             duration_ms=record.duration_ms, error_code=record.error_code)
        raise
    active(db, run)  # Keep a completed provider record even if the user stopped meanwhile.
    return value


def execute(db, run):
    from app.services.dialogue_routing import decide, route_reply, resolve_target
    from app.canvas_schemas import ResolveEdit
    payload = AgentInput.model_validate(run.request)
    active(db, run)
    task, ambiguous = resolve_target(db, run.project_id, task_id=payload.task_id)
    if payload.task_id is None:
        task = None  # never silently make an unrelated latest task the edit target
    route = decide(payload.text, has_result=bool(task or payload.document_id))
    if route in {"report_issue", "status", "question", "cancel"}:
        answer = route_reply(db, payload.text, task, ambiguous and not payload.task_id)
        return {"kind": "answer", "reply": answer["reply"], "evidence": answer.get("evidence", []), "children": [], "image_calls": 0}
    nodes = []
    if payload.document_id:
        doc = canvas.document(db, run.project_id, payload.document_id)
        ver = canvas.version(db, doc, payload.version_id)
        nodes = [{k: n[k] for k in ("id", "role", "text", "box", "locked") if k in n} for n in ver.content["nodes"]]
        if payload.replacement is not None:
            return {"kind": "edit", **canvas.resolve_edit(db, doc, ResolveEdit(version_id=ver.id,
                selected_object_id=payload.object_id, message=payload.text, replacement=payload.replacement)), "image_calls": 0}
    decision = None
    if payload.approved_text_calls:
        context = parent_context(payload, route, nodes)
        data = call_role(db, run, "parent", model_gateway.load_prompt("agent_parent_v1.md"), context)
        decision = AgentDecision.model_validate(data)
        if any(k not in LABELS or c.quote not in payload.text or c.value not in c.quote for k,c in decision.facts.items()):
            fail("FACT_EVIDENCE_INVALID", "模型事实缺少本轮原文证据，没有开始生成")
        if decision.intent in {"answer", "clarify", "inspect"}:
            return {"kind": "clarify" if decision.intent == "clarify" else "answer", "reply": decision.reply,
                    "children": [{"role":"parent", "status":"completed"}], "image_calls": 0}
        if decision.intent == "edit_text":
            if not payload.document_id:
                return {"kind":"clarify", "reply":"请先打开目标作品并选择要修改的文字。", "image_calls":0}
            # Never trust a parent-invented target. Resolver also checks ambiguity and version.
            proposed_id = payload.object_id or decision.target_object_id
            if proposed_id and not any(n["id"] == proposed_id for n in nodes):
                fail("INVALID_EDIT_TARGET", "目标对象不存在，没有修改")
            return {"kind":"edit", **canvas.resolve_edit(db, doc, ResolveEdit(version_id=ver.id,
                selected_object_id=proposed_id, message=payload.text, replacement=decision.replacement)), "image_calls":0}
    if route == "unclear" or route not in {"new_creation"}:
        return {"kind":"clarify", "reply":"请明确是查看问题、修改选中的文字，还是新建作品；没有启动生图。", "image_calls":0}
    # Only the same locally guarded intake creates a draft. Model output cannot bypass it.
    from app.creation_api import create, intake
    from app.services.intake import CreateInput, IntakeInput
    facts = {**({k:c.value for k,c in decision.facts.items()} if decision else {}), **payload.facts}
    draft = decision.creative_draft if decision else None
    children = [{"role":"parent", "status":"completed", "executor":"qwen" if decision else "rules"}]
    if decision and payload.approved_text_calls >= 2:
        from app.services.copy_policy import COPY_PE
        candidate = call_role(db, run, "copy", COPY_PE.read_text(encoding="utf-8") +
            '\n只返回JSON {"headline":"24字内","subheadline":"36字内"}。没有依据的事实不写。',
            {"facts":facts, "output_type":payload.output_type, "style":payload.style})
        from app.services.creative_workflow import copy_draft_valid
        if not copy_draft_valid(candidate, facts):
            fail("COPY_REVIEW_REQUIRED", "文案未通过事实或容量校验，请调整；没有开始生图")
        draft = candidate
        children.append({"role":"copy", "status":"completed", "executor":"qwen"})
    active(db, run)
    created = create(run.project_id, CreateInput(mode="pro" if payload.entry_mode == "professional" else "oneclick"), db)
    text = payload.text
    output = "full_plan" if payload.entry_mode == "fullplan" else payload.output_type
    if output == "detail":
        text += f"\n详情页{payload.detail_count}张"
    reviewed = intake(run.project_id, created["creation_id"], IntakeInput(expected_revision=0, text=text,
        answers=facts, asset_ids=payload.asset_ids, style=payload.style, output_type=output, output_selection="explicit",
        delivery_types=payload.delivery_types if output == "full_plan" else None,
        show_price=payload.show_price, show_store_name=payload.show_store_name,
        allow_illustration=payload.allow_illustration, use_ai=False), f"agent_{run.id}", db)
    if draft:
        from app.models import IntakeRevision
        from app.services.creative_workflow import copy_draft_valid
        row = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == created["creation_id"], IntakeRevision.revision == reviewed["revision"]))
        if copy_draft_valid(draft, row.snapshot["facts"]):
            row.snapshot = {**row.snapshot, "creative_draft": draft}
            row.snapshot_hash = digest(row.snapshot)
            db.commit()
            reviewed = {**reviewed, "snapshot": row.snapshot, "snapshot_hash": row.snapshot_hash}
    children.append({"role":"planner", "executor":"program", "status":"completed"})
    return {"kind":"review", "reply":"请核对本次资料和交付范围；只有确认后才调用图片模型。",
            "review":reviewed, "children":children, "image_calls":0}


def parent_context(payload, route, nodes):
    """New creation has no object requirement. Edit context is a separate contract."""
    from app.services.layout_catalog import OUTPUT_SPECS
    result = {"text":payload.text, "facts":payload.facts, "entry_mode":payload.entry_mode,
              "action_candidate":route, "output_type":payload.output_type,
              "delivery_types":payload.delivery_types if payload.entry_mode == "fullplan" else [payload.output_type],
              "output_spec":OUTPUT_SPECS[payload.output_type], "style":payload.style,
              "allow_illustration":payload.allow_illustration, "show_price":payload.show_price,
              "asset_count":len(payload.asset_ids), "layout_owner":"program_template_library",
              "workflow_kind":"new_creation" if route == "new_creation" else "resolve_edit"}
    if route != "new_creation" and payload.document_id:
        result.update(objects=nodes, selected_object_id=payload.object_id, version_id=payload.version_id)
    return result


def run_job(run_id):
    with SessionLocal() as db:
        changed = db.execute(update(AgentRun).where(AgentRun.id == run_id, AgentRun.state == "QUEUED")
            .values(state="RUNNING", lease_until=utc_now()+timedelta(minutes=5)))
        db.commit()
        if not changed.rowcount:
            return
        run = db.get(AgentRun, run_id)
        task = db.get(WorkflowTask, run.task_id)
        claimed_task = db.execute(update(WorkflowTask).where(WorkflowTask.id == run.task_id,
            WorkflowTask.status == TaskStatus.PENDING).values(status=TaskStatus.RUNNING))
        db.commit()
        if not claimed_task.rowcount:
            return
        started = time.monotonic()
        emit(db, run.project_id, run.id, "agent_queue", "completed")
        emit(db, run.project_id, run.id, "agent_workflow", "started")
        try:
            result = execute(db, run)
            active(db, run)
            changed = db.execute(update(AgentRun).where(AgentRun.id == run.id, AgentRun.state == "RUNNING")
                .values(state="SUCCEEDED", result=result, lease_until=None))
            if not changed.rowcount:
                db.rollback()
                return
            task.status, task.result, task.progress = TaskStatus.SUCCEEDED, result, 100
        except Exception as exc:
            db.rollback()
            db.refresh(run)
            db.refresh(task)
            if run.state != "RUNNING":
                return
            changed = db.execute(update(AgentRun).where(AgentRun.id == run.id, AgentRun.state == "RUNNING")
                .values(state="NEEDS_USER", lease_until=None))
            if not changed.rowcount:
                db.rollback()
                return
            task.status = TaskStatus.NEEDS_USER
            task.error_code = getattr(exc, "code", "AGENT_REVIEW_REQUIRED")
            detail = exc.detail if isinstance(exc, HTTPException) else None
            task.error_message = detail.get("message") if isinstance(detail, dict) else getattr(exc, "safe_message", "任务未完成，请核对输入与调用记录；没有自动重试。")
        run.lease_until = None
        db.commit()
        emit(db, run.project_id, run.id, "agent_workflow", "completed" if run.state == "SUCCEEDED" else "failed",
            duration_ms=max(1, int((time.monotonic()-started)*1000)), error_code=task.error_code)


def recover(db):
    expired = db.scalars(select(AgentRun).where(AgentRun.state == "RUNNING", AgentRun.lease_until < utc_now())).all()
    for run in expired:
        changed = db.execute(update(AgentRun).where(AgentRun.id == run.id, AgentRun.state == "RUNNING",
            AgentRun.lease_until < utc_now()).values(state="NEEDS_USER", lease_until=None))
        if changed.rowcount:
            task = db.get(WorkflowTask, run.task_id)
            task.status, task.error_code = TaskStatus.NEEDS_USER, "AGENT_RESULT_UNKNOWN"
            task.error_message = "执行中断，未自动重发语言或图片请求；请核对调用记录。"
    db.commit()
