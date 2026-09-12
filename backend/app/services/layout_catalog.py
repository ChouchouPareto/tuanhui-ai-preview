"""Normalized whole-canvas layouts. Export slices are deliberately absent."""
from copy import deepcopy
from hashlib import sha256

CATALOG_VERSION = "layout-regions-v1"
OUTPUT_SPECS = {
    "five_panel": {"ratio": "20:3", "size": [4000, 600], "slices": 5},
    "three_panel": {"ratio": "12:3", "size": [2400, 600], "slices": 3},
    "logo": {"ratio": "4:3", "size": [800, 600], "slices": 1, "safe_area": [.125, 0, .75, 1]},
    "package_main": {"ratio": "4:3", "size": [800, 600], "slices": 1, "safe_area": [.125, 0, .75, 1]},
    "voucher_main": {"ratio": "4:3", "size": [800, 600], "slices": 1, "safe_area": [.125, 0, .75, 1]},
    "dish": {"ratio": "4:3", "size": [800, 600], "slices": 1},
    "promotion": {"ratio": "4:3", "size": [800, 600], "slices": 1},
    "store_decoration": {"configured": False},
    "detail": {"configured": False},
}
FULL_PLAN_DEFAULTS = ["voucher_main", "five_panel", "logo"]


def region(role, box, allowed, required=False):
    return {"role": role, "box": list(box), "allowed": allowed, "required": required,
            "visible_border": False}


def layout(key, name, text_box, visual_boxes, accent_box):
    return {"id": key, "name": name, "outputs": ["five_panel", "three_panel"],
            "regions": [
                region("copy", text_box, ["品牌名", "主标题", "短文案", "已确认价格"]),
                *[region("visual", box, ["授权菜品素材", "主题示意静物"], True) for box in visual_boxes],
                region("accent", accent_box, ["已验证Logo线索", "插画", "图案素材"], False)],
            "rules": ["一张完整画布，不显示区域边框", "主视觉有主次，允许区域内尺度与位置变化",
                      "同一色调、材质、字体层级与光影", "没有Logo不生成虚假官方标识",
                      "不把输出裁切边界解释为构图区", "缺少辅助素材时留出呼吸空间，不发明真实菜品"]}


# Original region specifications; no third-party pixels or fonts are bundled.
LAYOUTS = [
    layout("L01", "左文右主视觉", (.03,.15,.25,.68), [(.32,.06,.64,.88)], (.03,.02,.12,.1)),
    layout("L02", "右文左主视觉", (.72,.15,.25,.68), [(.03,.06,.63,.88)], (.85,.02,.12,.1)),
    layout("L03", "中置标题两侧呼应", (.39,.14,.23,.72), [(.02,.06,.32,.88),(.66,.1,.32,.83)], (.46,.02,.08,.1)),
    layout("L04", "左主菜中标题右辅菜", (.33,.15,.24,.7), [(.01,.03,.28,.94),(.61,.16,.36,.76)], (.4,.02,.08,.1)),
    layout("L05", "左辅菜中标题右主菜", (.43,.15,.24,.7), [(.03,.16,.35,.76),(.71,.03,.28,.94)], (.5,.02,.08,.1)),
    layout("L06", "左文右双菜错落", (.03,.14,.24,.72), [(.31,.02,.35,.92),(.69,.2,.28,.68)], (.04,.02,.08,.1)),
    layout("L07", "右文左双菜错落", (.73,.14,.24,.72), [(.03,.2,.28,.68),(.34,.02,.35,.92)], (.87,.02,.08,.1)),
    layout("L08", "中左文两端静物", (.25,.15,.24,.7), [(.01,.22,.2,.68),(.53,.04,.44,.92)], (.32,.02,.08,.1)),
    layout("L09", "中右文两端静物", (.51,.15,.24,.7), [(.03,.04,.44,.92),(.79,.22,.2,.68)], (.59,.02,.08,.1)),
    layout("L10", "左侧品牌右三素材", (.02,.15,.22,.7), [(.28,.17,.2,.66),(.51,.03,.24,.94),(.78,.2,.2,.66)], (.07,.02,.08,.1)),
    layout("L11", "右侧品牌左三素材", (.76,.15,.22,.7), [(.02,.2,.2,.66),(.25,.03,.24,.94),(.52,.17,.2,.66)], (.84,.02,.08,.1)),
    layout("L12", "中央品牌两翼不对称", (.42,.15,.2,.72), [(.01,.04,.36,.92),(.67,.23,.3,.64)], (.48,.02,.08,.1)),
]


def select_layout(facts, output_type="five_panel", asset_count=0):
    candidates = [x for x in LAYOUTS if output_type in x["outputs"]]
    if asset_count:
        candidates = [x for x in candidates if sum(r["role"] == "visual" for r in x["regions"]) <= asset_count]
    if not candidates:
        raise ValueError("该输出类型尚无已审核构图模板，不能自由生成")
    seed = str(facts.get("store_name") or facts.get("hero_item") or "default")
    picked = deepcopy(candidates[int(sha256(seed.encode()).hexdigest()[:8], 16) % len(candidates)])
    picked["catalog_version"] = CATALOG_VERSION
    picked["selection"] = "deterministic_catalog_match"
    return picked


def validate_layout(value):
    canonical = next((x for x in LAYOUTS if x["id"] == value.get("id")), None)
    if canonical is None or canonical["regions"] != value.get("regions") or canonical["rules"] != value.get("rules"):
        raise ValueError("构图必须来自已登记模板库，不得自由替换区域约束")
