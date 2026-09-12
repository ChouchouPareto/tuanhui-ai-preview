"""M1 deterministic intake; no hidden provider calls or project-memory writes."""
import hashlib
import json
import re
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy import select

from app.models import Creation, FactVersion, IntakeRevision, SourceAsset, StoreProject


LABELS = {"store_name": "店名", "hero_item": "本次重点", "positioning": "门店特色", "selling_points": "真实卖点", "hero_price": "价格"}
ALIASES = {"store_name": "店名|门店名称|门店|店铺名称", "hero_item": "本次重点|主推菜品或套餐|主推菜品|主推套餐|主推内容|招牌菜|主推|菜名|菜品", "positioning": "门店特色|门店定位|特色|定位", "selling_points": "特色与卖点|主推荐卖点|主推卖点|真实卖点|核心卖点|卖点", "hero_price": "真实价格|套餐价格|价格|售价"}


class CreateInput(BaseModel):
    mode: Literal["oneclick", "pro"] = "oneclick"
    output_type: Literal["five_panel"] = "five_panel"


class IntakeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    text: str = Field(default="", max_length=8000)
    asset_ids: list[str] = Field(default_factory=list, max_length=20)
    answers: dict[str, str] = Field(default_factory=dict)
    show_price: bool = False
    show_store_name: bool | None = None
    style: Literal["appetite", "brand", "street", "minimal"] = "appetite"
    provider: Literal["qwen", "doubao"] = "qwen"
    use_ai: bool = False
    allow_illustration: bool = False
    accepted_understanding_policy: Literal["text-understanding-paid-v1"] | None = None
    input_mode: Literal["merge", "replace", "reply", "chat"] = "merge"
    reply_field: Literal["store_name", "hero_item", "positioning", "selling_points", "hero_price"] | None = None


class ConfirmInput(BaseModel):
    expected_revision: int = Field(ge=1)
    snapshot_hash: str = Field(min_length=64, max_length=64)
    accepted_budget_policy: Literal["local-paid-generation-v1"]
    materials_confirmed: bool


def fail(code, message, status=409):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require_creation(db, project_id, creation_id):
    creation = db.get(Creation, creation_id)
    if not creation or creation.project_id != project_id:
        fail("NOT_FOUND", "创作不存在", 404)
    return creation


def selected_assets(db, project_id, ids):
    result = []
    for asset_id in dict.fromkeys(ids):
        asset = db.get(SourceAsset, asset_id)
        if not asset or asset.project_id != project_id:
            fail("ASSET_NOT_FOUND", "所选素材不存在或不属于当前项目", 404)
        if not Path(asset.storage_path).is_file():
            fail("ASSET_FILE_MISSING", "所选素材文件缺失，请重新上传")
        with Path(asset.storage_path).open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != asset.sha256:
                fail("ASSET_CONTENT_CHANGED", "素材文件已变化，请重新上传并确认")
        result.append(asset)
    return result


def asset_manifest(assets):
    return [{"id": a.id, "name": a.original_name, "sha256": a.sha256, "role": a.semantic_role,
             "usage": "renderable" if a.asset_type == "product" and a.semantic_role in {"dish", "signature_dish"} else "recognition_only"}
            for a in assets]


def parse_text(text):
    values = {}
    # Conservative clause extraction: accept common explicit expressions, not guessed facts.
    for clause in re.split(r"[\n；;，,。！!]", text):
        clause = clause.strip()
        # Common short requests should not require a labelled form or another turn.
        short_name = re.fullmatch(r"(?:请)?(?:帮我|给我|给)?\s*([\u4e00-\u9fffA-Za-z0-9·]{2,24}(?:面馆|餐厅|饭店|火锅店|咖啡店|云饺))(?:做|制作|生成|设计)?(?:一套|一组)?(?:团购|首页)?(?:五连图|五图|5张图|五张图)?", clause)
        if short_name:
            values["store_name"] = short_name[1]
        focus = re.fullmatch(r"(?:这次|本次)?(?:想|希望)?(?:突出|主打|强调)\s*(.+)", clause)
        if focus and not re.search(r"^(?:不|待定|不知道)", focus[1]):
            values["selling_points"] = focus[1].strip()
        for key, labels in ALIASES.items():
            match = re.match(rf"^(?:我的|我们|这次|本次|请把|把)?\s*(?:{labels})\s*(?::|：|改为|改成|换成|叫做|叫|是|为|做)?\s*(.+)$", clause)
            if match:
                value = match[1].strip(" ：:")
                if value and len(value) <= 500 and not re.search(r"^(?:不|没有|待定|待确认|不知道|未定|不确定|待补充|待识别)", value):
                    values[key] = value
        named = re.match(r"^(?:我的|我们)?(?:店|店铺|餐厅)(?:叫做|叫|名叫)\s*(.+)$", clause)
        if named:
            values["store_name"] = named[1].strip()
        price = re.fullmatch(r"(?:套餐|双人餐)?\s*(\d+(?:\.\d{1,2})?)\s*元", clause)
        if price:
            values["hero_price"] = price[1] + "元"
    return values


def evaluate(facts, manifest, show_price=False, show_store_name=True, *, asset_led=False):
    has_dish = any(a["usage"] == "renderable" for a in manifest)
    fields = [] if (asset_led and has_dish) or any(str(facts.get(key) or "").strip() for key in ("hero_item", "selling_points", "positioning")) else ["hero_item"]
    if show_store_name:
        fields.insert(0, "store_name")
    if show_price:
        fields.append("hero_price")
    gaps = [{"field": key, "question": f"请填写{LABELS[key]}", "kind": "text"} for key in fields if not str(facts.get(key) or "").strip()]
    if show_price and facts.get("hero_price") and (not re.search(r"\d", str(facts["hero_price"])) or any(x in str(facts["hero_price"]) for x in ["未定", "待确认", "不知道"])):
        gaps.append({"field": "hero_price", "question": "请填写已确认的真实价格，或取消展示价格", "kind": "text"})
    if not has_dish:
        gaps.append({"field": "assets", "question": "请在上方上传或选择至少一张真实菜品图；门头和菜单不能替代", "kind": "asset"})
    return gaps


def conversation_reply(gaps, facts):
    if not gaps:
        focus = facts.get("hero_item") or facts.get("selling_points") or facts.get("positioning")
        if focus:
            return f"明白了，就突出{focus}，做成一套连续五图。"
        if facts.get("store_name"):
            return f"好，给{facts['store_name']}做一套五图。我来安排画面和文案；没有实拍时用AI示意，不编造价格或优惠。"
        return "照片收到了，我会用这些菜品做一套连续五图。"
    fields = {g["field"] for g in gaps}
    questions = []
    if "hero_item" in fields:
        if not facts.get("store_name"):
            questions.append("想给什么店做图？说个品类或想突出的内容就行。")
        elif "assets" not in fields:
            questions.append("这次想突出什么？也可以先做品牌主题。")
    if "store_name" in fields:
        questions.append("图片上写哪个店名？也可以告诉我不放店名。")
    if "hero_price" in fields:
        questions.append("价格用多少？不想放价格也可以直接说。")
    questions.extend(g["question"] for g in gaps if g["kind"] == "conflict")
    if "assets" in fields:
        questions.append("发张想放进画面的菜品照片吧。门头我只用来识别，不会放进成品。")
    return "\n".join(dict.fromkeys(questions))


def compile_intake(db, creation, payload):
    if payload.use_ai and not payload.accepted_understanding_policy:
        fail("AI_AUTHORIZATION_REQUIRED", "智能理解需先明确同意本次模型费用，不会自动调用")
    if any(key not in LABELS or len(value) > 500 for key, value in payload.answers.items()):
        fail("INVALID_ANSWERS", "补充字段不支持或内容过长", 422)
    old = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation.id, IntakeRevision.revision == creation.revision))
    message = payload.text.strip()
    chat = payload.input_mode == "chat"
    if chat:
        previous_text = old.snapshot["text"] if old else ""
        combined = "\n".join(part for part in (previous_text, message) if part)
        if len(combined) > 8000:
            fail("INPUT_TOO_LONG", "这次对话较长，请开始一次新创作；已有内容会保留", 422)
        payload = payload.model_copy(update={"text": combined})
    manifest = asset_manifest(selected_assets(db, creation.project_id, payload.asset_ids))
    memory = db.scalar(select(FactVersion).where(FactVersion.project_id == creation.project_id, FactVersion.confirmed_at.is_not(None)).order_by(FactVersion.version.desc()))
    facts = {key: value for key, value in (memory.facts if memory else {}).items() if key in LABELS}
    sources = {key: "project_confirmed" for key in facts}
    if old and payload.input_mode != "replace":
        facts.update(old.snapshot["facts"])
        sources.update(old.snapshot["sources"])
    extracted = parse_text(payload.text)
    uncertain = []
    if payload.use_ai:
        from app.services.intake_understanding import understand
        from app.services.model_gateway import ModelGatewayError
        try:
            understood = understand(db, creation, payload.text, digest(payload.model_dump()))
        except ModelGatewayError as exc:
            fail(exc.code, exc.safe_message)
        extracted.update(understood["facts"])
        uncertain = understood["uncertain_fields"]
        for key in uncertain:
            extracted.pop(key, None)
            facts.pop(key, None)
    text = payload.text.strip()
    if payload.input_mode == "reply":
        if not old:
            fail("REPLY_WITHOUT_CONTEXT", "请先提交创作需求", 422)
        if payload.reply_field and not extracted and payload.reply_field not in uncertain:
            value = text.strip()
            if not value or len(value) > 500 or re.search(r"不知道|不确定|待定|随便|你决定", value):
                fail("ANSWER_UNRESOLVED", "这项信息还无法确定，请在原输入框补充真实内容", 422)
            extracted[payload.reply_field] = value
            text = f"{LABELS[payload.reply_field]}：{value}"
        text = old.snapshot["text"] + "\n" + text
    if len(text) > 8000:
        fail("INPUT_TOO_LONG", "需求过长，请精简后重新提交", 422)
    facts.update(extracted)
    sources.update({key: "user_text" for key in extracted})
    facts.update({key: value.strip() for key, value in payload.answers.items()})
    sources.update({key: "user_answer" for key in payload.answers})
    show_price = payload.show_price
    show_store = payload.show_store_name if payload.show_store_name is not None else (bool(facts.get("store_name")) if creation.mode == "oneclick" else True)
    if payload.input_mode != "merge":
        show_price = bool(extracted.get("hero_price")) if payload.input_mode in {"replace", "chat"} else bool(old and old.snapshot["show_price"])
        show_store = show_store if payload.input_mode in {"replace", "chat"} else bool(old and old.snapshot["show_store_name"])
        if extracted.get("hero_price"):
            show_price = True
        for directive in re.finditer(r"(不展示|不显示|不标注|不写|不放|不要显示|不要展示|不要|展示|显示|标注|放上|写上)\s*(价格|店名)(?:\s*(?:和|与|、)\s*(价格|店名))?", payload.text):
            flag = not directive[1].startswith(("不", "不要"))
            for target in (directive[2], directive[3]):
                if target == "价格": show_price = flag
                elif target == "店名": show_store = flag
    else:
        show_price = show_price and (bool(payload.answers) or not re.search(r"不(?:展示|显示|标注|标|写)价格", payload.text))
    if not show_price:
        facts["hero_price"] = ""
    design_style = payload.style
    if chat:
        for clause in re.split(r"[\n；;，,。！!]", text):
            match = re.fullmatch(r"(?:请|想要|要)?(?:风格)?(?:换成|改成)?(温馨|烟火|简约|清爽|高级|品牌质感|有食欲)(?:一点|一些|风格)?", clause.strip())
            if match:
                design_style = {"温馨": "street", "烟火": "street", "简约": "minimal", "清爽": "minimal", "高级": "brand", "品牌质感": "brand", "有食欲": "appetite"}[match[1]]
    # Explicit UI policy: absent usable photos may use a labelled illustration.
    # Older clients retain their original real-photo requirement.
    illustration = payload.allow_illustration and creation.mode == "oneclick" and not any(a["usage"] == "renderable" for a in manifest)
    if chat:
        for clause in re.split(r"[\n；;，,。！!]", text):
            if re.fullmatch(r"(?:请)?(?:使用|做|生成|改成|选择|先做)\s*AI\s*示意图", clause.strip(), re.I):
                illustration = True
            elif re.search(r"(?:不用|不要|不做|不使用)(?:使用|做|生成)?\s*AI\s*示意图|使用真实照片", clause, re.I):
                illustration = False
    gaps = evaluate(facts, manifest, bool(show_price), show_store, asset_led=creation.mode == "oneclick")
    if illustration:
        gaps = [g for g in gaps if g["field"] != "assets"]
        if facts.get("store_name"):
            gaps = [g for g in gaps if g["field"] != "hero_item"]
        if not any(facts.get(key) for key in ("store_name", "hero_item", "selling_points", "positioning")) and not any(g["field"] == "hero_item" for g in gaps):
            gaps.append({"field": "hero_item", "question": "想做什么品类或主题的示意图？", "kind": "text"})
    for key in ("store_name", "hero_item", "selling_points", "positioning", "hero_price"):
        if (key == "store_name" and not show_store) or (key == "hero_price" and not show_price):
            continue
        if re.search(r"或者|还是|不确定|待定|或", str(facts.get(key, ""))):
            gaps.append({"field": key, "question": f"{LABELS[key]}有多个选择，请在原输入框明确本次使用哪一个", "kind": "conflict"})
    changes = [key for key in facts if memory and key in memory.facts and facts[key] != memory.facts[key] and sources.get(key) != "project_confirmed"]
    messages = list(old.snapshot.get("messages", []) if old else []) if chat else []
    if chat and old and not messages and old.snapshot["text"]:
        messages.append({"role": "user", "content": old.snapshot["text"]})
    if chat:
        messages.append({"role": "user", "content": message or "使用这些素材做五图"})
        messages.append({"role": "assistant", "content": conversation_reply(gaps, facts)})
    return {"schema_version": 2, "text": text, "messages": messages, "render_mode": "illustration" if illustration else "real_assets", "facts": facts, "sources": sources,
            "design_references": {"brand_color": memory.facts.get("brand_color"), "source": "confirmed_project_facts", "fact_version": memory.version} if memory and memory.facts.get("brand_color") else {},
            "assets": manifest, "show_price": bool(show_price), "show_store_name": show_store,
            "style": design_style, "provider": payload.provider, "gaps": gaps,
            "project_changes": changes, "scope": "this_creation_only", "ready": not gaps,
            "interpretation": "ai_grounded_text" if payload.use_ai else "rules_and_user_confirmation", "budget_policy": "local-paid-generation-v1"}


def review(db, creation):
    item = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation.id, IntakeRevision.revision == creation.revision))
    return {"creation_id": creation.id, "revision": creation.revision, "status": creation.status, "project_name": db.get(StoreProject, creation.project_id).name,
            "snapshot_hash": item.snapshot_hash if item else "", "snapshot": item.snapshot if item else None}
