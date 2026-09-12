"""Reject model-drawn text before program typography. OCR is a guard, not a proof."""
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path


def detector_binary():
    if platform.system() != "Darwin" or not shutil.which("swiftc"):
        raise ValueError("本地文字检查器尚未配置，未开始付费生图。部署到其他系统时须配置对应 OCR 检查器。")
    source = Path(__file__).with_name("recognize_text.swift")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    directory = Path(tempfile.gettempdir()) / "tuanhui-ocr"
    directory.mkdir(mode=0o700, exist_ok=True)
    binary = directory / f"vision-{digest}"
    if not binary.exists():
        # Compile once per source version, then reuse; concurrent builds use unique files.
        with tempfile.TemporaryDirectory(prefix="build-", dir=directory) as temporary:
            output = Path(temporary) / "vision"
            try:
                subprocess.run(["swiftc", str(source), "-o", str(output)], check=True, timeout=90, capture_output=True)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ValueError("本地文字检查器准备失败，未开始付费生图。") from exc
            output.replace(binary)
    return binary


def detect_text(path):
    result = subprocess.run([str(detector_binary()), str(path)], capture_output=True, timeout=20, check=True)
    return json.loads(result.stdout)


def check_background(path):
    try:
        observations = detect_text(path)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError("文字检查未完成，未叠加文案，也未自动重新生图。原结果已保存供排查。") from exc
    # Ignore isolated symbols/noise; reject recognizable words, numerals or Chinese text.
    words = [r for r in observations if r.get("confidence", 0) >= .35 and
             sum(c.isalnum() for c in r.get("text", "")) >= 2]
    report = {"engine": "macOS-Vision", "status": "rejected" if words else "passed",
              "detected_text": words, "limitation": "OCR may miss stylized text; not a semantic quality guarantee"}
    Path(path).with_name("text-guard.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if words:
        raise ValueError("底图出现了模型绘制的文字，已拦截重复排字。原底图已保留，没有自动扣费重试。")
    return report
