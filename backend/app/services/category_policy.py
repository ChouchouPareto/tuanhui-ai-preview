"""Small, versioned category packs. Inference is a design hint, never a merchant fact."""
import re

VERSION = "category-pe-v1"
PACKS = {
    "food": {"name": "餐饮", "children": {
        "regional": "地方特色菜", "hotpot": "火锅", "bbq": "烧烤", "bar": "酒吧",
        "light_meal": "轻餐", "noodles": "面食", "dumplings": "饺子馄饨", "cafe": "咖啡茶饮"},
        "subject": "餐具与餐桌材质的主题静物，不推测具体菜单",
        "copy": ["把这一餐，留给好心情", "今天的相聚，从这里开始", "给日常，添一点滋味", "这一刻，慢慢享用", "下一餐，换个心情", "留点时间，好好吃饭"],
        "avoid": ["未经证实的现做、手工、新鲜、产地及销量承诺"]},
    "beauty": {"name": "丽人", "children": {"hair": "美发", "nails": "美甲", "skincare": "美容护理"},
        "subject": "护理工具与材质的抽象静物，不展示虚构疗效前后对比",
        "copy": ["给自己，一点焕新的时间", "让喜欢的风格，成为日常", "今天，把时间留给自己", "从细节，遇见新心情", "自己的风格，慢慢挑选", "留一点时间，照顾自己"],
        "avoid": ["治疗、逆龄、永久、效果保证及未经证实的资质"]},
    "leisure": {"name": "休闲娱乐", "children": {"games": "桌游娱乐", "sports": "运动", "spa": "休闲养生"},
        "subject": "与休闲主题有关的光影静物，不虚构场馆实景",
        "copy": ["把空闲，留给喜欢的事", "今天，换一种放松方式", "给日常，安排一点乐趣", "约个时间，一起出发", "这一刻，暂时放慢", "好心情，从相聚开始"],
        "avoid": ["虚构设施、医疗功效及安全绝对保证"]},
    "shopping": {"name": "购物", "children": {"retail": "零售", "flowers": "鲜花", "clothing": "服饰"},
        "subject": "陈列台与包装材质，不虚构具体品牌产品",
        "copy": ["把喜欢，带进日常", "为生活，挑一点心意", "今天，发现一点新意", "喜欢的细节，值得停留", "慢慢挑，选你喜欢", "给日常，一份新灵感"],
        "avoid": ["虚构折扣、库存、正品授权及销量"]},
    "general": {"name": "待明确类目", "children": {}, "subject": "抽象材质与光影，不推测商家经营内容",
        "copy": ["发现日常里的新意", "把喜欢，留在这一刻", "为今天，添一点灵感", "从这里，开始新体验", "给日常，换一种心情", "值得停留的一刻"], "avoid": ["臆测经营类目与商品事实"]},
}
RULES = [
    ("beauty", "nails", "美甲"), ("beauty", "hair", "美发|理发|发型"), ("beauty", "skincare", "美容|护理"),
    ("leisure", "games", "桌游|密室|剧本杀|KTV"), ("leisure", "sports", "健身|运动|球馆"),
    ("leisure", "spa", "足浴|按摩|SPA"), ("shopping", "flowers", "花店|鲜花"),
    ("shopping", "clothing", "服饰|服装"), ("shopping", "retail", "超市|零售|便利店"),
    ("food", "hotpot", "火锅"), ("food", "bbq", "烧烤|烤串"), ("food", "bar", "酒吧"),
    ("food", "light_meal", "轻餐|沙拉|轻食"), ("food", "noodles", "面馆|面条|拉面|刀削面"),
    ("food", "dumplings", "饺|馄饨"), ("food", "cafe", "咖啡|茶饮|奶茶"),
    ("food", "regional", "餐厅|餐饮|川菜|湘菜|小炒|饭店|粤菜|菜馆"),
]


def resolve_category(facts):
    text = " ".join(str(facts.get(k) or "") for k in ("hero_item", "positioning", "store_name"))
    explicit = facts.get("category_primary")
    for primary, secondary, pattern in RULES:
        if re.search(pattern, text, re.I):
            return {"primary": primary, "secondary": secondary, "source": "design_inference_not_business_fact", "version": VERSION}
    return {"primary": explicit if explicit in PACKS else "general", "secondary": None, "source": "explicit" if explicit in PACKS else "unknown", "version": VERSION}
