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
    # A type mentioned as an element/reference is not a requested deliverable.
    # In particular, a full-plan list must not collapse to its last item.
    selected = fallback
    explicit = []
    switches = []
    denied = set()
    for match in matches:
        prefix = text[max(0, match.start()-24):match.start()]
        suffix = text[match.end():match.end()+12]
        clause = re.split(r"[，。；;\n]", prefix)[-1]
        if re.search(r"参考|参照|借鉴|配色|标题|文案|角落|左上|右上|左下|右下|画面里|图中|图片里", clause):
            continue
        if re.search(r"[「『“\"]", prefix) and not re.search(r"[」』”\"]", prefix[prefix.rfind("「")+1:]):
            continue
        if re.search(r"(?:不要|不用|不做|不生成|不需要)\s*$", prefix):
            denied.add(names[match[0].lower()])
            continue
        if re.search(r"(?:放|加|添加|放置|包含|包括|参考|参照|沿用|保留|上传|使用|借鉴)(?:一[个张份]|这[个张份]|一下)?\s*$", prefix):
            continue
        if re.match(r"(?:的)?(?:配色|风格|布局|素材|元素|位置)", suffix):
            continue
        direction = names[match[0].lower()]
        if re.search(r"(?:改成|改为|换成|切换到|切换为|只做|只生成)\s*$", prefix):
            switches.append(direction)
        elif re.search(r"(?:做|制作|生成|设计|要)(?:一[张套份个]|个|张|套)?\s*$", prefix):
            explicit.append(direction)
        elif not text[:match.start()].strip() or (len(matches) == 1 and len(text) < 40 and not suffix.strip("。！! ")):
            explicit.append(direction)
    if switches:
        selected = switches[-1]
    elif explicit:
        # Switching is explicit; otherwise the leading requested work owns its list.
        selected = explicit[0]
    if selected in denied:
        raise ValueError("你排除了当前图片类型，请明确这次要制作哪一种；尚未开始理解或生成。")
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
