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


def build_design_plan(facts: dict, style: str = "appetite") -> dict:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["appetite"])
    store_name = _text(facts.get("store_name"), "") if facts.get("show_store_name", True) else ""
    hero_item = _text(facts.get("hero_item"), "")
    positioning = _text(facts.get("positioning"), "")
    raw_points = facts.get("selling_points", [])
    selling_points = [str(item).strip() for item in (raw_points if isinstance(raw_points, list) else [raw_points]) if str(item).strip()]
    focus = hero_item or (selling_points[0] if selling_points else positioning)
    hero_price = _text(facts.get("hero_price"), "") if facts.get("show_price", True) else ""
    primary_point = selling_points[0] if selling_points else positioning
    secondary_point = selling_points[1] if len(selling_points) > 1 else positioning
    frames = [
        {"index": 1, "role": "品牌主题", "headline": store_name, "support": positioning, "visual": "统一母版上的品牌文字；门头照片仅用于识别，禁止入画"},
        {"index": 2, "role": "本次重点", "headline": focus, "support": primary_point if primary_point != focus else "", "visual": "用已提供素材呈现本次重点，不把卖点或特色当作菜名，不虚构菜品"},
        {"index": 3, "role": "连续主视觉", "headline": primary_point, "support": secondary_point, "visual": "与左右相连的真实菜品素材区域，不生成独立场景"},
        {"index": 4, "role": "素材展示", "headline": focus, "support": primary_point if primary_point != focus else "", "visual": "按实际素材数量延展主视觉，不添加未提供的菜品或饮料"},
        {"index": 5, "role": "品牌收束", "headline": hero_price, "support": focus, "visual": "同一背景中的已确认文字信息，不生成店内环境"},
    ]
    return {
        "template_version": "continuous-food-master-v1",
        "canvas": {"ratio": "20:3", "recommended_size": "4000x600", "slice_count": 5, "slice_ratio": "4:3", "slice_size": "800x600"},
        "style": {"key": style, **deepcopy(preset)},
        "copy": {"headline": focus, "subheadline": primary_point if primary_point != focus else positioning, "store_name": store_name, "price": hero_price},
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
