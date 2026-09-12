"""Typed role hand-offs: one understanding call, deterministic planner, visual tool, local QA.

Roles are not four redundant LLM calls. Case images are NEVER in runtime envelopes.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
from sqlalchemy import select, update
from app.models import DesignPlan, StoreProject, utc_now
from app.services.category_policy import resolve_category, PACKS
from app.services.copy_policy import validate_copy

VERSION = "creative-workflow-v1"
ROLE_CONTRACTS = {
    "understanding": {"executor": "llm_or_rules", "input": ["current_message", "verified_context"], "output": ["evidence_backed_facts", "creative_draft"], "max_calls": 1},
    "planning": {"executor": "program", "input": ["facts", "category_pack", "eligible_templates", "recent_five"], "output": ["design_plan"], "max_calls": 0},
    "visual": {"executor": "image_model", "input": ["selected_layout", "style", "subject"], "output": ["wordless_master"], "max_calls": 1},
    "quality": {"executor": "local_ocr_and_geometry", "input": ["wordless_master", "copy", "layout"], "output": ["quality_report", "exports"], "max_calls": 0},
}


def reserve_context(db, project_id):
    """Caller keeps transaction through plan+task insert. Project row serializes reservations.

    SQLite obtains the write lock here; PostgreSQL obtains the row lock. Count queued,
    failed and successful new-image plans alike; text-only revisions do not consume one.
    """
    db.execute(update(StoreProject).where(StoreProject.id == project_id).values(updated_at=utc_now()))
    plans = db.scalars(select(DesignPlan).where(DesignPlan.project_id == project_id,
        DesignPlan.status == "CONFIRMED").order_by(DesignPlan.created_at.desc(), DesignPlan.version.desc())).all()
    recent = []
    for item in plans:
        if item.plan.get("execution", {}).get("kind") == "text_only":
            continue
        variants = item.plan.get("deliverables", [item.plan])
        layout_id = next((v.get("layout", {}).get("id") for v in variants if v.get("output_type") in {"five_panel", "three_panel"}), None)
        if layout_id:
            recent.append(layout_id)
        if len(recent) == 5:
            break
    return recent


def compact_layout(layout):
    """Allowlist prevents review paths, source images and lengthy case notes leaking out."""
    return {"id": layout["id"], "version": layout["catalog_version"],
        "coordinates": "normalized x,y,width,height; origin top-left",
        "regions": [{"role": r["role"], "box": r["box"], "direction":
            "empty low-detail area reserved for program typography" if r["role"] == "copy" else
            "primary/secondary subject; do not cover copy" if r["role"] == "visual" else "optional subtle decoration"}
            for r in layout["regions"]],
        "rules": layout["rules"]}


def copy_draft_valid(draft, facts):
    if not isinstance(draft, dict) or set(draft) - {"headline", "subheadline"}:
        return False
    if any(not isinstance(v, str) for v in draft.values()):
        return False
    text = " ".join(draft.values())
    if not draft.get("headline") or len(draft["headline"]) > 24 or len(draft.get("subheadline", "")) > 36:
        return False
    try:
        validate_copy(draft)
    except ValueError:
        return False
    evidence = " ".join(str(v) for v in facts.values())
    # Unverified factual promises never promoted from creative draft to copy.
    claims = re.findall(r"现做|现包|手工|新鲜|正宗|祖传|百年|低脂|零糖|有机|进口|免费|不限量|折扣|限时|销量|人气|招牌|推荐|第一|最好|保证|治疗|逆龄|永久|[0-9]+(?:\.[0-9]+)?", text)
    return all(claim in evidence for claim in claims)


def compose_copy(facts, category, selection_key="", draft=None):
    pack = PACKS[category["primary"]]
    index = int(sha256(selection_key.encode()).hexdigest()[:8], 16) % len(pack["copy"])
    name = str(facts.get("store_name") or "") if facts.get("show_store_name", True) else ""
    focus = facts.get("hero_item") or facts.get("selling_points") or facts.get("positioning") or ""
    focus = "、".join(map(str, focus)) if isinstance(focus, list) else str(focus)
    result = {"store_name": name, "headline": focus or pack["copy"][index], "subheadline": pack["copy"][index] if focus else "",
              "price": str(facts.get("hero_price") or "") if facts.get("show_price", True) else ""}
    if copy_draft_valid(draft, facts):
        result.update(draft)
    # Exact user-authored title edits have priority; still go through safety/capacity checks.
    if facts.get("copy_headline"):
        result["headline"] = facts["copy_headline"]
    seen = set()
    for key in ("store_name", "headline", "subheadline", "price"):
        value = result[key].strip()
        result[key] = "" if value in seen else value
        if value:
            seen.add(value)
    validate_copy(result)
    return result


def attach_workflow(plan, *, selection_key="", draft=None):
    result = deepcopy(plan)
    category = resolve_category(result["locked_facts"])
    result["category"] = category
    facts = {**result["locked_facts"], "show_store_name": bool(result["copy"].get("store_name"))}
    result["copy"] = compose_copy(facts, category, selection_key, draft)
    if category["primary"] != "food":
        result["creative_direction"]["subject"] = PACKS[category["primary"]]["subject"]
        result["creative_direction"]["category"] = "品牌主题" if category["primary"] == "general" else PACKS[category["primary"]]["name"]
    result["workflow"] = {"version": VERSION, "roles": ROLE_CONTRACTS,
        "reference_images_sent": False, "copy_source": "validated_model_draft" if copy_draft_valid(draft, facts) else "category_copy_pack",
        "retry_policy": "no_automatic_paid_retry", "category_pe_version": category["version"]}
    result["execution"] = {"kind": "new_image"}
    return result


def parse_copy_edit(message):
    if re.search(r"(?:再|同时|并且|顺便).*(?:换|改|加|删).*(?:图|配色|风格|素材|价格|店名)", message):
        return None
    match = re.fullmatch(r"\s*(?:请)?(?:只|仅)?(?:把)?(?:主标题|标题|文案)\s*(?:改成|改为|换成|换为|：|:)\s*[“\"]?(.+?)[”\"]?\s*[。]?\s*", message, re.S)
    return match[1].strip(" ：:") if match else None
