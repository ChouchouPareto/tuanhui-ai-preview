from copy import deepcopy


STYLE_PRESETS = {
    "appetite": {"name": "食欲冲击", "keywords": ["高饱和食欲色", "菜品近景", "热气氛围", "粗体标题"]},
    "brand": {"name": "品牌质感", "keywords": ["品牌主色", "留白克制", "材质细节", "官方表达"]},
    "street": {"name": "烟火市井", "keywords": ["暖棕底色", "暖色光影", "真实菜品", "生活化构图"]},
    "minimal": {"name": "清爽简约", "keywords": ["浅色背景", "信息聚焦", "简洁排版", "轻量装饰"]},
}


def _text(value, fallback="待确认") -> str:
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip()) or fallback
    normalized = str(value or "").strip()
    return normalized or fallback


def build_design_plan(facts: dict, style: str = "appetite", *, output_type="five_panel", asset_count=0,
                      excluded_ids=(), selection_key="", draft=None) -> dict:
    from app.services.layout_catalog import OUTPUT_SPECS, select_layout
    from app.services.copy_policy import validate_copy
    spec = deepcopy(OUTPUT_SPECS.get(output_type, {}))
    if not spec or spec.get("configured") is False:
        raise ValueError("输出规格尚未配置，不能自动推定")
    from app.services.output_contract import SINGLE_OUTPUTS, single_layout
    layout = single_layout(output_type) if output_type in SINGLE_OUTPUTS else select_layout(facts, output_type, asset_count, excluded_ids=excluded_ids, selection_key=selection_key)
    creative = creative_direction(facts)
    store_name = _text(facts.get("store_name"), "") if facts.get("show_store_name", True) else ""
    focus = _text(facts.get("hero_item"), "") or _text(facts.get("selling_points"), "") or _text(facts.get("positioning"), "")
    copy = {"store_name": store_name, "headline": focus or creative["headline"],
            "subheadline": _text(facts.get("positioning"), ""),
            "price": _text(facts.get("hero_price"), "") if facts.get("show_price", True) else ""}
    validate_copy(copy)
    result = {
        "template_version": "region-master-v3", "output_type": output_type,
        "canvas": {"ratio": spec["ratio"], "recommended_size": f'{spec["size"][0]}x{spec["size"][1]}',
                   "slice_count": spec["slices"], "slice_ratio": "4:3", "slice_size": "800x600"},
        "layout": layout, "style": {"key": style, **deepcopy(STYLE_PRESETS.get(style, STYLE_PRESETS["appetite"]))},
        "copy": copy, "copy_policy_version": "copywriting-v2",
        # Compatibility metadata for existing review UI; never used as composition regions.
        "frames": [{"index": i+1, "role": f"导出切片{i+1}", "headline": "", "support": "",
                    "visual": "完整设计输出后的裁切区域，不约束构图"} for i in range(spec["slices"])],
        "creative_direction": creative,
        "locked_facts": {"store_name": store_name, "hero_item": _text(facts.get("hero_item"), ""),
                         "positioning": _text(facts.get("positioning"), ""),
                         "selling_points": facts.get("selling_points") if isinstance(facts.get("selling_points"), list) else ([facts["selling_points"]] if facts.get("selling_points") else []), "hero_price": copy["price"],
                         "copy_headline": facts.get("copy_headline"), "category_primary": facts.get("category_primary")},
        "guardrails": ["事实不可编造", "不得编造价格与优惠", "门头原图绝不入画", "构图必须来自模板库", "整体风格一致"],
    }
    from app.services.creative_workflow import attach_workflow
    result = attach_workflow(result, selection_key=selection_key, draft=draft)
    if output_type == "logo":
        result["creative_direction"]["subject"] = "原创品牌图形标识草案，简洁可辨的抽象符号，不仿制已有商标，不绘制任何文字"
        result["copy"] = {"store_name":store_name, "headline":"" if store_name else "品牌标识", "subheadline":"", "price":""}
    if output_type == "voucher_main":
        result["copy"]["headline"] = "代金券"
        result["copy"]["subheadline"] = ""  # Never fabricate value, selling price or conditions.
    return result


def creative_direction(facts):
    """A labelled visual interpretation, kept separate from locked business facts."""
    topic = " ".join(_text(facts.get(k), "") for k in ("store_name", "hero_item", "positioning"))
    categories = [
        (("面馆", "面条", "拉面", "刀削面"), "面食", "今天，来一碗面", "一碗面食与面条纹理的食欲特写"),
        (("云饺", "饺子", "水饺", "馄饨"), "饺子与馄饨", "这一餐，想吃点暖的", "饺子或馄饨的示意造型与餐碗特写"),
        (("火锅",), "火锅", "围坐一桌，享受这一刻", "火锅餐桌与锅中食材的示意特写"),
        (("咖啡",), "咖啡", "给自己，一杯的时间", "咖啡杯与咖啡色层次的特写"),
        (("烧烤", "烤串"), "烧烤", "今晚，一起吃点好的", "烤串与炭火色调的示意特写"),
        (("鱼",), "鱼类餐饮", "今天，换一种好滋味", "鱼料理的示意餐盘特写"),
    ]
    category, headline, subject = "品牌主题", "发现你的下一餐", "精致餐碗、筷子与餐桌材质组成的餐饮静物"
    for keys, category_name, title, visual in categories:
        if any(key in topic for key in keys):
            category, headline, subject = category_name, title, visual
            break
    if facts.get("hero_item"):
        subject = f"围绕用户提供的本次重点「{_text(facts['hero_item'], '')}」设计主题静物；非菜品主题不能画成菜名"
    return {
        "category": category, "headline": headline, "subject": subject, "source": "creative_interpretation_not_menu",
        "visuals": [
            f"品牌开场，{subject}，主体偏右",
            f"主视觉，{subject}，近景突出质感",
            f"细节视角，{subject}，特写与光影层次",
            f"用餐氛围，{subject}，俯拍与留白构成",
            f"收束画面，{subject}，简洁餐桌静物",
        ],
        "policy": "只作AI示意，不代表真实菜单、门店实拍或官方品牌资产；不编造价格、优惠和经营承诺",
    }


def validate_design_plan(plan):
    from app.services.layout_catalog import validate_layout, OUTPUT_SPECS
    from app.services.copy_policy import validate_copy
    if plan.get("template_version") == "region-master-v3":
        from app.services.output_contract import SINGLE_OUTPUTS, validate_single_layout
        if plan.get("output_type") in SINGLE_OUTPUTS:
            validate_single_layout(plan.get("layout", {}), plan["output_type"])
        else:
            validate_layout(plan.get("layout", {}))
        spec = OUTPUT_SPECS.get(plan.get("output_type"), {})
        expected_size = "x".join(map(str, spec.get("size", [])))
        if plan.get("output_type") not in plan["layout"]["outputs"] or plan["canvas"]["ratio"] != spec.get("ratio") or plan["canvas"]["slice_count"] != spec.get("slices") or plan["canvas"]["recommended_size"] != expected_size:
            raise ValueError("输出规格与模板不一致")
        validate_copy(plan["copy"])
        return
    # Keep previously confirmed snapshots readable; new plans never use this branch.
    frames = plan.get("frames", [])
    if len(frames) != 5 or any(not f.get("headline") for f in frames):
        raise ValueError("历史方案不完整")


def update_design_plan(plan: dict, *, style: str | None = None, headline: str | None = None, subheadline: str | None = None) -> dict:
    updated = deepcopy(plan)
    if style:
        preset = STYLE_PRESETS[style]
        updated["style"] = {"key": style, **deepcopy(preset)}
    if headline:
        updated["copy"]["headline"] = headline
        if len(updated["frames"]) > 1:
            updated["frames"][1]["headline"] = headline
    if subheadline:
        updated["copy"]["subheadline"] = subheadline
        if len(updated["frames"]) > 1:
            updated["frames"][1]["support"] = subheadline
    return updated
