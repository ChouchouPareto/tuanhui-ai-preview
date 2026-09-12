"""Build immutable owner-review artifacts from the SAME registry used at runtime.

Run PYTHONPATH=backend .venv/bin/python scripts/export_template_review.py --version v0.11.0
No reference pixels are bundled in runtime JSON. Each export uses exclusive creation.
"""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from app.services.layout_catalog import ALL_LAYOUTS, catalog_entry, OUTPUT_SPECS
from app.services.category_policy import PACKS
from app.services.creative_workflow import ROLE_CONTRACTS

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    {"id":"G01","file":"大众点评餐饮点评五连图.png","logic":"深底高对比，四组餐盘主次错落，竖向标签辅助","transfer":"深浅对比、主体尺度变化","exclude":"品牌、文案、销量与食材品质承诺","boxes":[["文字层级",.01,.05,.23,.35],["主素材",.01,.28,.24,.65],["次素材",.38,.16,.25,.78],["辅助素材",.64,.13,.17,.79],["辅助素材",.82,.09,.17,.82]]},
    {"id":"G02","file":"大众点评餐饮点评五连图 (1).png","logic":"左侧品牌标题，右侧四组产品，蓝色统一背景","transfer":"左文右图、曲线视觉动线、冷暖对比","exclude":"海鲜品名、招牌必点标签、特定水花组合","boxes":[["品牌与主标题",.02,.12,.15,.75],["产品A",.19,.25,.18,.64],["产品B",.40,.07,.15,.80],["产品C",.60,.23,.17,.65],["产品D",.79,.12,.19,.74]]},
    {"id":"G03","file":"大众点评餐饮点评五连图 (2).png","logic":"左前景主菜，中左大标题，右侧三组菜品","transfer":"大标题与主菜平衡、前后景层次","exclude":"具体手写字形、月亮树枝组合、品牌菜名","boxes":[["左前景主菜",.00,.34,.20,.65],["核心文案",.10,.08,.32,.70],["辅菜A",.43,.23,.18,.70],["辅菜B",.60,.03,.20,.84],["辅菜C",.80,.06,.20,.86]]},
    {"id":"G04","file":"大众点评餐饮点评五连图 (3).png","logic":"红色活泼基底，中左文案，右侧餐盘节奏排列","transfer":"主体高低错落、对比色点缀","exclude":"每日现捕等承诺、装饰波纹组合、案例文字","boxes":[["品牌主视觉",.01,.18,.12,.70],["核心文案",.14,.10,.22,.72],["产品A",.37,.22,.15,.66],["产品B",.52,.25,.18,.64],["产品C",.72,.30,.13,.58],["产品D",.86,.20,.14,.72]]},
    {"id":"G05","file":"大众点评餐饮点评五连图 (4).png","logic":"左侧贴纸式标题，右侧三锅，黑底与暖色对比","transfer":"信息层级、粗细对比、重复节奏","exclude":"撕纸与喇叭特定组合、手写字形、具体汤底事实","boxes":[["核心文案",.03,.12,.28,.76],["主视觉A",.34,.08,.20,.86],["主视觉B",.55,.04,.22,.92],["主视觉C",.77,.08,.22,.86]]},
    {"id":"G06","file":"红色川菜小炒餐厅中餐外卖大众点评团购图AIGC/五连图整理.png","logic":"左侧放大主菜，中间标题，右侧三组菜品前后叠放","transfer":"主次尺度、中心留字、右侧前后层次","exclude":"案例书法、推荐徽章、原店内照片和菜名","boxes":[["主菜",.02,.07,.20,.86],["核心文案",.26,.15,.245,.70],["辅菜A",.52,.06,.145,.61],["辅菜B前景",.65,.30,.145,.66],["辅菜C",.75,.04,.165,.64]]},
]


def export(version):
    folder = ROOT / "docs/pe/releases" / version
    folder.mkdir(parents=True,exist_ok=True)
    templates = [catalog_entry(x) for x in ALL_LAYOUTS]
    payload = {"release":version,"owner_review":"pending","templates":templates,
               "category_packs":PACKS,"roles":ROLE_CONTRACTS,"outputs":OUTPUT_SPECS,
               "reference_policy":"原案例只给人审核，运行时禁止发送原案例像素、路径、品牌文案"}
    raw = json.dumps(payload,ensure_ascii=False,indent=2)
    with (folder/"runtime-contract.json").open("x") as f: f.write(raw)
    with (folder/"case-review-only.json").open("x") as f: f.write(json.dumps(CASES,ensure_ascii=False,indent=2))
    text = [f"# 模板审核包 {version}","",f"运行规则 SHA256：{sha256(raw.encode()).hexdigest()}","",
            "状态：内部预览；所有模板待用户视觉审核，不能标记为用户已批准。", "",
            "Figma：https://www.figma.com/design/3NScJVMCFE33Ec7lI5iVyW", "",
            "两层严格隔离：案例拆解只作人工理解；runtime-contract.json 是同一运行注册表导出的结构规则，不含参考图。", "",
            "18种为构图家族，不等于18种风格。L01–L12保留旧区域，L13–L18补充单素材构图。新版本没有声称已复刻稿定成品。", ""]
    for c in CASES:
        text += [f"## 案例 {c['id']}","",f"来源：素材案例/来源：稿定设计/{c['file']}","",
                 f"观察：{c['logic']}。",f"可抽象：{c['transfer']}。",f"不可沿用：{c['exclude']}。", "",
                 "坐标为人工估测，用于职责拆解，不是原设计文件测量值；不据此逐像素描摹。", ""]
    for t in templates:
        text += [f"## {t['id']} · {t['name']}","", "```json",json.dumps(t,ensure_ascii=False,indent=2),"```", ""]
    with (folder/"模板坐标与案例审核.md").open("x") as f: f.write("\n".join(text))
    print(folder)


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--version",required=True)
    args=parser.parse_args()
    if not args.version.replace(".","").replace("-","").isalnum(): raise ValueError("Invalid version")
    export(args.version)
