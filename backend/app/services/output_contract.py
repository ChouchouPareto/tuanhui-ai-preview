"""Output adapters, not a new composition library or an editable canvas."""
import re

NAMES = {"five_panel":"五连图", "three_panel":"三连图", "logo":"Logo图", "package_main":"套餐主图",
         "voucher_main":"代金券主图", "dish":"菜品单品图", "promotion":"团购宣传图",
         "store_decoration":"首页装修图", "detail":"详情页", "full_plan":"全案"}
SINGLE_OUTPUTS = set(NAMES) - {"five_panel", "three_panel", "full_plan"}


def detect_output(text, fallback="five_panel"):
    names = {"三连图":"three_panel", "三图":"three_panel", "3连图":"three_panel", "五连图":"five_panel", "五图":"five_panel", "5连图":"five_panel",
             "logo":"logo", "套餐主图":"package_main", "代金券":"voucher_main", "菜品单品图":"dish", "单品图":"dish", "推荐菜":"dish",
             "团购宣传图":"promotion", "宣传图":"promotion", "首页装修图":"store_decoration", "封面图":"store_decoration", "详情页":"detail", "全案":"full_plan"}
    matches = list(re.finditer("|".join(map(re.escape, sorted(names,key=len,reverse=True))), text, re.I))
    selected = fallback
    for match in matches:
        if not re.search(r"不要|不用|不做", text[max(0,match.start()-4):match.start()]):
            selected = names[match[0].lower()]
    return selected


def single_layout(output):
    # Fixed output safe-area adapter. These are not case-derived visual templates.
    safe = output in {"logo", "package_main", "voucher_main"}
    left, width = (.15,.70) if safe else (.05,.90)
    return {"id":"output-safe-area-v1", "catalog_version":"output-safe-area-v1", "outputs":[output],
            "regions":[{"role":"visual", "box":[left,.05,width,.49], "allowed":["主题视觉"], "required":False, "visible_border":False},
                       {"role":"copy", "box":[left,.59,width,.35], "allowed":["已核对文案"], "required":False, "visible_border":False}],
            "rules":["单张4:3完整画布", "核心内容限定中央1:1区域，装饰可延伸" if safe else "主体和文字不得相互遮挡", "保持统一风格，不显示区域框"]}


def validate_single_layout(layout, output):
    if layout != single_layout(output):
        raise ValueError("单图输出安全区域被改动")
