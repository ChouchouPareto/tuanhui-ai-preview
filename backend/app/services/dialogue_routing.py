"""Zero-provider-call safety routing and evidence-only inspection.

This is a conservative first-stage gate, not a general semantic Agent. Unclear
follow-ups ask for scope instead of defaulting to a paid image request.
"""
import json
import re
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.models import CreationConfirmation, IntakeRevision, ModelCallRecord, TaskStatus, WorkflowTask
from app.services.intake import fail, require_creation

VERSION = "dialogue-safety-v1.1"


def decide(text, *, has_result=False):
    value = text.strip()
    # Quoted copy may itself contain a question. An explicit, supported title
    # edit is not an enquiry, unless the surrounding request also reports a fault.
    issue = re.search(r"重叠|叠字|乱码|错字|裁断|裁掉|截断|遮挡|打不开|下载不了|看不了|没出来|无法生成|生成失败|报错|有问题|出问题|还是这样|不满意|不好看|太丑|很丑|不对劲|不符合|不像|不对|不行|图不对", value)
    inquiry = re.search(r"为什么|为何|怎么回事|什么原因|解释|分析|检查|排查|看看|看一下|看下|请问|能不能|可不可以|能否|你觉得|怎么样|是否|会不会|[？?]|吗[，。！!\s]*$", value)
    negative = re.search(r"(?:不要|别|不用|先不|暂不|不想|不需要|不准).{0,8}(?:生成|重做|重生|生图|出图)|仅(?:解释|询问)|只是(?:想)?问", value)
    if re.fullmatch(r"(?:请|先|帮我)?\s*(?:停止生成|停止|停一下|取消生成|取消|不做了|取消，不做了)[。！!\s]*", value):
        return "cancel"
    if re.search(r"多久|进度|做到哪|排队|还没(?:出图|生成)|花了多长|耗时|用了.*模型|哪个模型|多少.*[钱费]|[Tt]oken|费用|花费", value) and not issue:
        return "status" if has_result else "question"
    if issue:
        return "report_issue"
    if negative:
        return "question"
    from app.services.creative_workflow import parse_copy_edit
    if has_result and parse_copy_edit(value):
        return "edit_copy"
    if inquiry or re.search(r"有什么区别|有什么不同|包括什么|怎么用|如何|介绍一下|告诉我原因", value):
        return "question"
    if re.fullmatch(r"(?:你好|您好|谢谢|辛苦了|在吗)[！!。\s]*", value):
        return "question"
    # First-turn action requests must not fall through to descriptive intake.
    # These workflows need their own target/permission/context contracts; until
    # those are available, clarify without pretending to have executed them.
    if re.search(r"^(?:请|帮我|麻烦)?\s*(?:确认)?(?:删除|隐藏|恢复|复制|打开|导出|下载|识别|提取)", value):
        return "unclear"
    if re.search(r"(?:刚才|之前|上次|原来)的(?:店名|价格|文案|素材|信息)|(?:那个|其他|另一个)项目", value):
        return "unclear"
    if re.fullmatch(r"(?:请|帮我)?(?:用|选择|换成|引用|拿来)(?:这个|这张|那个|那张).{0,12}(?:图|照片|素材)[。！!\s]*", value):
        return "unclear"
    if re.search(r"(?:别|不要|不能).{0,6}(?:一样|相同|重复)", value):
        return "unclear"
    if has_result and re.fullmatch(r"(?:请)?(?:换|改)(?:成|一个)?(?:清爽|简约|温馨|烟火|品牌质感|食欲冲击)(?:一点|一些|的)?(?:风格)?[。！!\s]*", value):
        return "new_creation"
    if re.search(r"(?:重(?:新)?(?:生成|做)|再(?:生成|做)|生成|制作|设计|做).{0,35}(?:图|版|海报|封面|logo|Logo)|重新生成|重新做一版", value):
        return "new_creation"
    if has_result:
        # Do not turn arbitrary feedback or unsupported local edits into full regeneration.
        return "unclear"
    if re.fullmatch(r"(?:好的?|嗯|确认|同意|继续|再来(?:一下)?|随便)[。！!\s]*", value):
        return "unclear"
    return "new_creation"  # Fresh descriptive intake still accepts a brand/subject/photos.


def resolve_target(db, project_id, creation_id=None, task_id=None):
    creation = require_creation(db, project_id, creation_id) if creation_id else None
    confirmation = db.scalar(select(CreationConfirmation).where(CreationConfirmation.creation_id == creation.id,
        CreationConfirmation.revision == creation.revision)) if creation else None
    # A draft may inherit an explicit parent. Never substitute the project's latest task.
    if creation and not confirmation:
        revision = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation.id,
            IntakeRevision.revision == creation.revision))
        parent = (revision.snapshot if revision else {}).get("parent_creation_id")
        if parent:
            require_creation(db, project_id, parent)
            confirmation = db.scalar(select(CreationConfirmation).where(CreationConfirmation.creation_id == parent))
    task = db.get(WorkflowTask, task_id) if task_id else (db.get(WorkflowTask, confirmation.task_id) if confirmation else None)
    if task_id and (not task or task.project_id != project_id or task.task_type != "group_buying_image_generation"):
        fail("TARGET_NOT_FOUND", "找不到当前项目的这版作品，请从项目中重新打开。", 404)
    if task and task.project_id != project_id:
        fail("TARGET_NOT_FOUND", "这版作品不属于当前项目。", 404)
    if task_id and creation and (not confirmation or confirmation.task_id != task_id):
        fail("TARGET_CONFLICT", "当前对话和作品不是同一版，请重新选择要查看的作品。")
    if not task and not creation:
        candidates = db.scalars(select(WorkflowTask).where(WorkflowTask.project_id == project_id,
            WorkflowTask.task_type == "group_buying_image_generation").limit(2)).all()
        if len(candidates) == 1:
            task = candidates[0]
        elif len(candidates) > 1:
            return None, True
    return task, False


def inspect_task(db, task):
    """Read saved evidence only; no OCR subprocess, repair, model call or source overwrite."""
    evidence = [{"kind": "task", "status": task.status.value, "progress": task.progress, "error_code": task.error_code}]
    calls = db.scalars(select(ModelCallRecord).where(ModelCallRecord.task_id == task.id)).all()
    evidence.extend({"kind": "model_call", "model": c.model, "provider": c.provider, "status": c.status,
                     "duration_ms": c.duration_ms, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens} for c in calls)
    root = Path(settings.generated_dir).resolve()
    directory = (root / task.project_id / task.id).resolve()
    if not directory.is_relative_to(root):
        fail("INVALID_ARTIFACT_PATH", "作品文件位置无法核对，未执行任何修改。")
    files = {}
    for name in ("model-visual.png", "long.png", "text-guard.json", "generation-audit.json", "generation-request.json"):
        candidate = (directory / name).resolve()
        files[name] = candidate.is_relative_to(directory) and candidate.is_file()
    evidence.append({"kind": "saved_files", **files})
    guard = None
    if files["text-guard.json"]:
        try:
            source = directory / "text-guard.json"
            if source.stat().st_size <= 200_000:
                report = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(report, dict) and report.get("status") in {"passed", "rejected"}:
                    guard = report["status"]
                    evidence.append({"kind": "text_guard", "status": guard})
        except (OSError, ValueError):
            pass
    return evidence, files, guard


def route_reply(db, text, task=None, ambiguous=False):
    intent = decide(text, has_result=bool(task) or ambiguous)
    target = {"task_id": task.id if task else None, "project_id": task.project_id if task else None}
    result = {"schema_version": VERSION, "intent": intent, "action": "answer", "can_prepare": False,
              "target": target, "evidence": [], "reply": "", "next_steps": [], "model_calls": 0}
    if ambiguous:
        result.update(intent="unclear", action="clarify", reply="这个项目里有多版作品。请先打开想处理的那一版，再告诉我哪里需要调整；我还没有重新生成。")
        return result
    if intent in {"new_creation", "edit_copy"} and not (task and task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}):
        result.update(action="prepare", can_prepare=True)
        return result
    if intent == "cancel":
        result.update(action="cancel", reply="请点击输入框旁的「停止生成」。已发送的请求可能仍会计费，停止不会重新提交任务。" if task else "目前没有定位到正在生成的任务，没有发起新的调用。")
        return result
    if not task:
        result.update(reply="我可以先帮你了解流程，不会直接生图。生成前会核对本次费用；已有作品的问题，请先打开对应作品，我才能检查它的实际记录。" if intent == "question" else "你是想新做一张图，还是检查已有作品？说清这一步就好，我暂时没有生成图片。", action="clarify")
        return result
    evidence, files, guard = inspect_task(db, task)
    result["evidence"] = evidence
    state = {TaskStatus.PENDING: "还在排队", TaskStatus.RUNNING: "正在处理", TaskStatus.SUCCEEDED: "已完成生成", TaskStatus.NEEDS_USER: "已停止或需要处理", TaskStatus.FAILED_FINAL: "这次没有完成"}[task.status]
    if intent == "status":
        model_calls = [e for e in evidence if e["kind"] == "model_call"]
        models = "、".join(dict.fromkeys(e["model"] for e in model_calls))
        details = f"记录的模型是 {models}。" if models else "这版没有可核对的模型调用记录，不能用当前默认配置代替。"
        result["reply"] = f"这版{state}，记录进度 {task.progress}%。{details}费用没有准确账单记录时不能推算为免费；没有重新提交生成。"
    elif intent == "report_issue":
        if guard == "rejected":
            result["reply"] = "查到了：这版保存的文字检查记录显示，模型底图里已经出现文字。直接再排一层字会有重叠风险，不能靠简单叠字消除。我没有重生或覆盖这版作品。"
        elif task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            result["reply"] = f"查到这版{state}，还没有完成交付。先保留当前任务，不会因这条反馈重复生成。"
        elif not files["model-visual.png"]:
            result["reply"] = "我查了这版的记录，但没有找到可核对的原始底图，暂时不能断定是模型绘字、排字还是预览问题。旧作品保留，没有重新生成。"
        else:
            result["reply"] = "我查到了这版的原始底图和任务记录。" + ("已有文字检查通过记录，但这不能证明没有漏检或排版问题。" if guard == "passed" else "还缺少能确认原因的文字检查证据。") + "目前不能把重叠原因说死，也没有重新生成。"
        result["next_steps"] = ["在上方预览这版图片，指出具体文字或区域。" if files["long.png"] else "这次没有可交付的预览；已保留的原始内容仅用于问题核对，不当作合格作品。", "若已有成功作品且只是改标题，可输入「标题改成……」；其他修复先明确范围，不自动整图重做。"]
    elif task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
        result["reply"] = "这版仍在处理中。我没有新增生成任务；你可以继续询问进度，或点击「停止生成」。"
    elif intent == "question":
        result["reply"] = "这条我按咨询处理，不会自动再生图。当前支持查看记录和明确改标题；需要换画面时再明确提出生成要求，并核对费用。"
    else:
        result.update(action="clarify", reply="你想保留画面只改文字，还是重新做一版？如果是在反馈问题，直接说哪里不对就好，我会先查看这版记录，不会直接生成。")
    return result


def guard_intake_message(text, *, has_result=False):
    intent = decide(text, has_result=has_result)
    if intent not in {"new_creation", "edit_copy"}:
        fail("DIALOGUE_ACTION_REQUIRED", "这条是咨询、反馈或范围未明确的修改，没有开始生图。请在对话中先查看记录或明确要修改的内容。")
    return intent
