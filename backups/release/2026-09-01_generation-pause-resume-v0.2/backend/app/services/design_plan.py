from copy import deepcopy


STYLE_PRESETS = {
    "appetite": {"name": "食欲冲击", "keywords": ["高饱和食欲色", "菜品近景", "热气氛围", "粗体标题"]},
    "brand": {"name": "品牌质感", "keywords": ["品牌主色", "留白克制", "材质细节", "官方表达"]},
    "street": {"name": "烟火市井", "keywords": ["门店实景", "暖色灯光", "真实就餐感", "生活化构图"]},
    "minimal": {"name": "清爽简约", "keywords": ["浅色背景", "信息聚焦", "简洁排版", "轻量装饰"]},
}


def _text(value, fallback="待确认") -> str:
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip()) or fallback
    normalized = str(value or "").strip()
    return normalized or fallback


def build_design_plan(facts: dict, style: str = "appetite") -> dict:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["appetite"])
    store_name = _text(facts.get("store_name"))
    hero_item = _text(facts.get("hero_item"))
    positioning = _text(facts.get("positioning"))
    selling_points = [str(item).strip() for item in facts.get("selling_points", []) if str(item).strip()]
    hero_price = _text(facts.get("hero_price"), "价格不展示")
    primary_point = selling_points[0] if selling_points else positioning
    secondary_point = selling_points[1] if len(selling_points) > 1 else positioning
    frames = [
        {"index": 1, "role": "品牌开场", "headline": store_name, "support": positioning, "visual": "门头或品牌标识，建立门店识别"},
        {"index": 2, "role": "主推菜", "headline": hero_item, "support": primary_point, "visual": "主推菜大图，突出真实食材与食欲感"},
        {"index": 3, "role": "核心卖点", "headline": primary_point, "support": secondary_point, "visual": "菜品细节与制作氛围，强化可信卖点"},
        {"index": 4, "role": "套餐价值", "headline": hero_price, "support": hero_item, "visual": "套餐组合或菜单信息，价格只使用已确认内容"},
        {"index": 5, "role": "到店收束", "headline": store_name, "support": positioning, "visual": "门店环境或招牌菜组合，完成品牌记忆"},
    ]
    return {
        "canvas": {"ratio": "20:3", "recommended_size": "4000x600", "slice_count": 5, "slice_ratio": "4:3", "slice_size": "800x600"},
        "style": {"key": style, **deepcopy(preset)},
        "copy": {"headline": hero_item, "subheadline": primary_point, "store_name": store_name, "price": hero_price},
        "frames": frames,
        "locked_facts": {
            "store_name": store_name,
            "positioning": positioning,
            "hero_item": hero_item,
            "hero_price": hero_price,
            "selling_points": selling_points,
        },
        "guardrails": ["不得改写门店名称", "不得编造价格与优惠", "不得添加未确认资质或功效", "正文文字由排版层渲染，不由生图模型绘制"],
    }


def update_design_plan(plan: dict, *, style: str | None = None, headline: str | None = None, subheadline: str | None = None) -> dict:
    updated = deepcopy(plan)
    if style:
        preset = STYLE_PRESETS[style]
        updated["style"] = {"key": style, **deepcopy(preset)}
    if headline:
        updated["copy"]["headline"] = headline
        updated["frames"][1]["headline"] = headline
    if subheadline:
        updated["copy"]["subheadline"] = subheadline
        updated["frames"][1]["support"] = subheadline
    return updated
