"""M1 deterministic intake; no hidden provider calls or project-memory writes."""
import hashlib
import json
import re
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy import select

from app.models import Creation, FactVersion, IntakeRevision, SourceAsset


LABELS = {"store_name": "店名", "hero_item": "主推菜品", "positioning": "门店特色", "selling_points": "真实卖点", "hero_price": "价格"}
ALIASES = {"store_name": "店名|门店名称|门店", "hero_item": "主推菜品|主推内容|主推|菜名|菜品", "positioning": "门店特色|定位", "selling_points": "真实卖点|核心卖点|卖点", "hero_price": "价格|售价|套餐价格"}


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
    show_store_name: bool = True
    style: Literal["appetite", "brand", "street", "minimal"] = "appetite"
    provider: Literal["qwen", "doubao"] = "qwen"
    use_ai: bool = False


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
    for key, labels in ALIASES.items():
        matches = re.findall(rf"(?:^|[\n；;，,])\s*(?:{labels})\s*[:：]\s*([^\n；;，,]+)", text)
        if matches:
            values[key] = matches[-1].strip()
    return values


def evaluate(facts, manifest, show_price=False, show_store_name=True):
    fields = ["hero_item"]
    if show_store_name:
        fields.insert(0, "store_name")
    if show_price:
        fields.append("hero_price")
    gaps = [{"field": key, "question": f"请填写{LABELS[key]}", "kind": "text"} for key in fields if not str(facts.get(key) or "").strip()]
    if show_price and facts.get("hero_price") and (not re.search(r"\d", str(facts["hero_price"])) or any(x in str(facts["hero_price"]) for x in ["未定", "待确认", "不知道"])):
        gaps.append({"field": "hero_price", "question": "请填写已确认的真实价格，或取消展示价格", "kind": "text"})
    if not any(a["usage"] == "renderable" for a in manifest):
        gaps.append({"field": "assets", "question": "请在上方上传或选择至少一张真实菜品图；门头和菜单不能替代", "kind": "asset"})
    return gaps


def compile_intake(db, creation, payload):
    if payload.use_ai:
        fail("AI_INTAKE_NOT_ENABLED", "AI整理费用与真实模型验收尚未启用；请填写确认卡，不会调用模型")
    if any(key not in LABELS or len(value) > 500 for key, value in payload.answers.items()):
        fail("INVALID_ANSWERS", "补充字段不支持或内容过长", 422)
    old = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation.id, IntakeRevision.revision == creation.revision))
    memory = db.scalar(select(FactVersion).where(FactVersion.project_id == creation.project_id, FactVersion.confirmed_at.is_not(None)).order_by(FactVersion.version.desc()))
    facts = {key: value for key, value in (memory.facts if memory else {}).items() if key in LABELS}
    sources = {key: "project_confirmed" for key in facts}
    if old:
        facts.update(old.snapshot["facts"])
        sources.update(old.snapshot["sources"])
    extracted = parse_text(payload.text)
    facts.update(extracted)
    sources.update({key: "user_text" for key in extracted})
    facts.update({key: value.strip() for key, value in payload.answers.items()})
    sources.update({key: "user_answer" for key in payload.answers})
    show_price = payload.show_price and (bool(payload.answers) or not re.search(r"不(?:展示|显示|标注|标|写)价格", payload.text))
    if not show_price:
        facts["hero_price"] = ""
    manifest = asset_manifest(selected_assets(db, creation.project_id, payload.asset_ids))
    gaps = evaluate(facts, manifest, bool(show_price), payload.show_store_name)
    changes = [key for key in facts if memory and key in memory.facts and facts[key] != memory.facts[key] and sources.get(key) != "project_confirmed"]
    return {"schema_version": 1, "text": payload.text, "facts": facts, "sources": sources,
            "assets": manifest, "show_price": bool(show_price), "show_store_name": payload.show_store_name,
            "style": payload.style, "provider": payload.provider, "gaps": gaps,
            "project_changes": changes, "scope": "this_creation_only", "ready": not gaps,
            "interpretation": "rules_and_user_confirmation", "budget_policy": "local-paid-generation-v1"}


def review(db, creation):
    item = db.scalar(select(IntakeRevision).where(IntakeRevision.creation_id == creation.id, IntakeRevision.revision == creation.revision))
    return {"creation_id": creation.id, "revision": creation.revision, "status": creation.status,
            "snapshot_hash": item.snapshot_hash if item else "", "snapshot": item.snapshot if item else None}
