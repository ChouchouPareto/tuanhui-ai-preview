"""Normalized whole-canvas layouts. Export slices are deliberately absent."""
from copy import deepcopy
from hashlib import sha256

CATALOG_VERSION = "layout-regions-v2"
OUTPUT_SPECS = {
    "five_panel": {"ratio": "20:3", "size": [4000, 600], "slices": 5},
    "three_panel": {"ratio": "12:3", "size": [2400, 600], "slices": 3},
    "logo": {"ratio": "4:3", "size": [800, 600], "slices": 1, "safe_area": [.125, 0, .75, 1]},
    "package_main": {"ratio": "4:3", "size": [800, 600], "slices": 1, "safe_area": [.125, 0, .75, 1]},
    "voucher_main": {"ratio": "4:3", "size": [800, 600], "slices": 1, "safe_area": [.125, 0, .75, 1]},
    "dish": {"ratio": "4:3", "size": [800, 600], "slices": 1},
    "promotion": {"ratio": "4:3", "size": [800, 600], "slices": 1},
    "store_decoration": {"ratio": "4:3", "size": [800, 600], "slices": 1},
    "detail": {"ratio": "4:3", "size": [800, 600], "slices": 1},
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


# Keep the first twelve geometries immutable for old confirmed snapshots.
EXTENDED_LAYOUTS = [
    layout("L13", "左侧小标题右侧宽景", (.03,.26,.19,.55), [(.27,.05,.70,.90)], (.03,.05,.10,.1)),
    layout("L14", "右侧小标题左侧宽景", (.78,.26,.19,.55), [(.03,.05,.70,.90)], (.84,.05,.10,.1)),
    layout("L15", "左侧宽标题右侧聚焦", (.03,.20,.38,.64), [(.47,.08,.49,.84)], (.04,.04,.10,.1)),
    layout("L16", "右侧宽标题左侧聚焦", (.59,.20,.38,.64), [(.04,.08,.49,.84)], (.86,.04,.10,.1)),
    layout("L17", "左侧紧凑标题右侧低位主体", (.05,.11,.27,.55), [(.39,.20,.56,.76)], (.06,.73,.10,.1)),
    layout("L18", "右侧紧凑标题左侧低位主体", (.68,.11,.27,.55), [(.05,.20,.56,.76)], (.83,.73,.10,.1)),
]
ALL_LAYOUTS = LAYOUTS + EXTENDED_LAYOUTS


def catalog_entry(value):
    result = deepcopy(value)
    result.update(catalog_version=CATALOG_VERSION, schema_version=2,
                  review_status="pending_owner_review", release_channel="internal_preview",
                  coordinate_system="normalized_xywh_top_left", reference_policy="review_only_never_model_input",
                  categories=["food", "beauty", "leisure", "shopping", "general"],
                  typography={"renderer": "program", "hierarchy": ["brand", "headline", "support", "price"],
                              "overflow": "fit_then_fail", "duplicate_text": "remove_exact_duplicate"})
    for index, item in enumerate(result["regions"]):
        item.update(id=f"{result['id']}_{index+1}", z_index=10 if item["role"] == "copy" else 1,
                    render_by="program" if item["role"] == "copy" else "visual_executor",
                    flexibility="区域内变化；不画边框、不遮挡文字")
    return result


def select_layout(facts, output_type="five_panel", asset_count=0, *, excluded_ids=(), selection_key=""):
    excluded = set(excluded_ids)
    candidates = [x for x in ALL_LAYOUTS if output_type in x["outputs"] and x["id"] not in excluded]
    if asset_count:
        candidates = [x for x in candidates if sum(r["role"] == "visual" for r in x["regions"]) <= asset_count]
    if not candidates:
        raise ValueError("当前没有符合素材数量且避开近五次使用记录的构图模板；不会重复或自由编造模板")
    seed = str(selection_key or facts.get("store_name") or facts.get("hero_item") or "default")
    picked = catalog_entry(candidates[int(sha256(seed.encode()).hexdigest()[:8], 16) % len(candidates)])
    picked["selection"] = "project_recent_five_excluded"
    picked["excluded_ids"] = list(excluded_ids)
    return picked


def validate_layout(value):
    canonical = next((x for x in ALL_LAYOUTS if x["id"] == value.get("id")), None)
    if canonical and value.get("catalog_version") == CATALOG_VERSION:
        canonical = catalog_entry(canonical)
    if canonical is None or canonical["regions"] != value.get("regions") or canonical["rules"] != value.get("rules"):
        raise ValueError("构图必须来自已登记模板库，不得自由替换区域约束")
