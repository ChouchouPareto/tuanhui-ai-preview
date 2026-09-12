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
    # Creative copy is not a business fact: use invitations, never invented claims.
    creative = creative_direction(facts)
    titles = [store_name or focus or "一餐的好心情", focus or creative["headline"],
              primary_point or "把这一餐留给自己", secondary_point or "约上喜欢的人",
              hero_price or "今天，就来这里"]
    supports = [positioning or "从这里，开启今天的美味",
                primary_point if primary_point != focus else "",
                secondary_point, "一起享受用餐时光", store_name or "发现你的下一餐"]
    for index, frame in enumerate(frames):
        frame.update(headline=titles[index], support=supports[index],
                     visual=creative["visuals"][index])
    return {
        "template_version": "continuous-food-master-v2",
        "canvas": {"ratio": "20:3", "recommended_size": "4000x600", "slice_count": 5, "slice_ratio": "4:3", "slice_size": "800x600"},
        "style": {"key": style, **deepcopy(preset)},
        "copy": {"headline": titles[1], "subheadline": supports[1], "store_name": store_name, "price": hero_price},
        "frames": frames,
        "creative_direction": creative,
        "locked_facts": {
            "store_name": store_name,
            "positioning": positioning,
            "hero_item": hero_item,
            "hero_price": hero_price,
            "selling_points": selling_points,
        },
        "guardrails": ["不得改写门店名称", "不得编造价格与优惠", "不得添加未确认资质或功效", "正文文字由排版层渲染，不由生图模型绘制"],
    }


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
        "category": category, "headline": headline, "source": "creative_interpretation_not_menu",
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
    frames = plan.get("frames", [])
    if len(frames) != 5 or [f.get("index") for f in frames] != list(range(1, 6)):
        raise ValueError("五图方案缺少完整的五个内容区域")
    if any(not str(f.get("headline", "")).strip() or not str(f.get("visual", "")).strip() for f in frames):
        raise ValueError("五图方案存在空标题或空画面规划，不能交付空背景")


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
