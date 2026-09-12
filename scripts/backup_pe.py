"""Append-only Markdown PE snapshots. Run before and after changing PE files."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    "backend/app/services/design_plan.py", "backend/app/services/layout_catalog.py",
    "backend/app/services/copy_policy.py", "backend/app/services/image_generation.py",
    "backend/app/services/master_layout.py", "backend/app/services/intake_understanding.py",
    "backend/app/services/model_gateway.py", "backend/app/services/analysis.py", "backend/app/schemas.py",
    "backend/app/services/intake.py", "backend/app/creation_api.py",
]


def backup(label="snapshot", destination=None):
    folder = Path(destination) if destination else ROOT / "docs/pe/backups"
    folder.mkdir(parents=True, exist_ok=True)
    label = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", label)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = folder / f"{stamp}_{label}_{uuid4().hex[:8]}.md"
    paths = [ROOT / f for f in SOURCES if (ROOT / f).is_file()]
    paths += sorted((ROOT / "backend/app/services/prompts").glob("*"))
    parts = [f"# PE工程快照：{label}\n\nUTC：{stamp}\n\n只增不覆盖；此文件不是运行入口。\n"]
    for path in paths:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        fence = chr(96) * 3
        parts.append(f"\n## {path.relative_to(ROOT)}\n\nSHA256：{sha256(raw).hexdigest()}\n\n{fence}\n{raw.decode('utf-8')}\n{fence}\n")
    # Exclusive create prevents replacing an existing file even on name collision.
    with target.open("x", encoding="utf-8") as output:
        output.write("".join(parts))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="snapshot")
    args = parser.parse_args()
    print(backup(args.label))
