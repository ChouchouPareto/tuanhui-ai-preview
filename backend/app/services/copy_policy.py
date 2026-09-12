"""Conservative copy checks. These do not certify legal compliance."""
from pathlib import Path
import re

COPY_PE = Path(__file__).with_name("prompts") / "copywriting_v2.md"


def validate_copy(copy):
    text = " ".join(str(v or "") for v in copy.values())
    if re.search(r"全网第一|全国第一|绝对最好|百分百有效|包治|根治|治愈|最便宜|吊打同行|秒杀同行", text):
        raise ValueError("文案含绝对化、功效或贬低表达，请调整后再生成")
    if len(str(copy.get("headline", ""))) > 60:
        raise ValueError("主标题超出模板文字容量，请精简表达")
    if not any(str(copy.get(k) or "").strip() for k in ("store_name", "headline")):
        raise ValueError("缺少可用的主题文案")
