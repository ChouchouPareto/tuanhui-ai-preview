import base64
import io
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DesignPlan, ModelCallRecord, ProjectStatus, SourceAsset, StoreProject, TaskStatus, WorkflowTask, utc_now


class ImageGenerationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reference_data(asset: SourceAsset) -> str:
    with Image.open(asset.storage_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=86, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def build_visual_prompt(plan: dict) -> str:
    locked = plan["locked_facts"]
    frame_notes = "；".join(f"第{item['index']}屏{item['role']}：{item['visual']}" for item in plan["frames"])
    return (
        f"为中国大陆本地生活团购首页制作一张横向连续五联视觉底图，整体宽高比20:3，五个4:3画面无缝连接。"
        f"门店类型与定位：{locked['positioning']}。主推内容：{locked['hero_item']}。"
        f"视觉风格：{plan['style']['name']}，{','.join(plan['style']['keywords'])}。"
        f"分屏安排：{frame_notes}。参考图片只用于保持真实菜品、门头、环境与品牌特征，不得替换菜品种类。"
        "画面中不要出现任何文字、字母、数字、价格、招牌字、Logo文字或水印，所有文字将在后期排版。"
        "专业商业摄影与本地生活团购头图质感，统一光影、统一色调、跨屏元素自然延续，每屏主体完整且切割线附近避免关键主体。"
    )


def _extract_qwen_image(payload: dict) -> str:
    try:
        content = payload["output"]["choices"][0]["message"]["content"]
        return next(item["image"] for item in content if item.get("image"))
    except (KeyError, IndexError, StopIteration, TypeError) as exc:
        raise ImageGenerationError("QWEN_BAD_OUTPUT", str(payload.get("message") or "千问未返回图片")) from exc


def call_qwen(prompt: str, references: list[SourceAsset]) -> bytes:
    if not settings.dashscope_api_key:
        raise ImageGenerationError("QWEN_NOT_CONFIGURED", "未配置百炼 DASHSCOPE_API_KEY")
    content = [{"image": _reference_data(asset)} for asset in references[:3]]
    content.append({"text": prompt})
    response = httpx.post(
        settings.qwen_image_base_url,
        headers={"Authorization": f"Bearer {settings.dashscope_api_key}", "Content-Type": "application/json"},
        json={"model": settings.qwen_image_model, "input": {"messages": [{"role": "user", "content": content}]}, "parameters": {"prompt_extend": True, "enable_thinking": True, "n": 1, "size": "2000*300", "negative_prompt": "文字，乱码，数字，水印，变形菜品，重复餐具", "watermark": False}},
        timeout=max(settings.model_timeout_seconds, 180),
    )
    if response.status_code >= 400:
        raise ImageGenerationError("QWEN_HTTP_ERROR", f"千问生图失败（HTTP {response.status_code}）")
    image_url = _extract_qwen_image(response.json())
    image_response = httpx.get(image_url, timeout=90)
    image_response.raise_for_status()
    return image_response.content


def call_doubao(prompt: str, references: list[SourceAsset]) -> bytes:
    if not settings.ark_api_key:
        raise ImageGenerationError("DOUBAO_NOT_CONFIGURED", "未配置豆包 ARK_API_KEY")
    images = [_reference_data(asset) for asset in references[:3]]
    body = {"model": settings.doubao_image_model, "prompt": prompt, "size": "2K", "response_format": "b64_json", "watermark": False}
    if images:
        body["image"] = images
    response = httpx.post(settings.ark_image_base_url, headers={"Authorization": f"Bearer {settings.ark_api_key}", "Content-Type": "application/json"}, json=body, timeout=max(settings.model_timeout_seconds, 180))
    if response.status_code >= 400:
        raise ImageGenerationError("DOUBAO_HTTP_ERROR", f"豆包生图失败（HTTP {response.status_code}）")
    try:
        item = response.json()["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        image_response = httpx.get(item["url"], timeout=90)
        image_response.raise_for_status()
        return image_response.content
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ImageGenerationError("DOUBAO_BAD_OUTPUT", "豆包未返回图片") from exc


def _font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size, index=1 if bold and candidate.endswith("PingFang.ttc") else 0)
    return ImageFont.load_default()


def render_and_slice(image_bytes: bytes, plan: dict, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(image_bytes)) as source:
        canvas = ImageOps.fit(source.convert("RGB"), (4000, 600), method=Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(canvas, "RGBA")
    title_font, support_font, role_font = _font(45, True), _font(22), _font(17, True)
    for frame in plan["frames"]:
        left = (frame["index"] - 1) * 800
        draw.rounded_rectangle((left + 34, 360, left + 766, 566), radius=22, fill=(0, 0, 0, 145))
        draw.text((left + 64, 382), frame["role"], font=role_font, fill=(255, 255, 255, 185))
        draw.text((left + 64, 417), frame["headline"][:16], font=title_font, fill="white", stroke_width=1, stroke_fill=(0, 0, 0, 100))
        draw.text((left + 64, 490), frame["support"][:26], font=support_font, fill=(255, 255, 255, 220))
    long_path = output_dir / "long.png"
    canvas.save(long_path, format="PNG", optimize=True)
    slices = []
    for index in range(5):
        path = output_dir / f"{index + 1:02d}.png"
        canvas.crop((index * 800, 0, (index + 1) * 800, 600)).save(path, format="PNG", optimize=True)
        slices.append(path.name)
    return {"long_image": long_path.name, "slices": slices, "width": 4000, "height": 600}


def run_generation(db: Session, project: StoreProject, task: WorkflowTask, plan: DesignPlan, provider: str, allow_fallback: bool):
    task.status = TaskStatus.RUNNING
    task.progress = 8
    project.status = ProjectStatus.GENERATING
    db.commit()
    assets = db.scalars(select(SourceAsset).where(SourceAsset.project_id == project.id).order_by(SourceAsset.is_hero.desc(), SourceAsset.priority, SourceAsset.created_at)).all()
    references = list(assets[:3])
    prompt = build_visual_prompt(plan.plan)
    providers = [provider]
    if allow_fallback:
        providers.append("doubao" if provider == "qwen" else "qwen")
    errors = []
    for candidate in list(dict.fromkeys(providers)):
        started = time.monotonic()
        record = ModelCallRecord(project_id=project.id, task_id=task.id, provider=candidate, model=settings.qwen_image_model if candidate == "qwen" else settings.doubao_image_model, contract="group_buying_long_image_v1", status="RUNNING")
        db.add(record)
        db.commit()
        try:
            raw = call_qwen(prompt, references) if candidate == "qwen" else call_doubao(prompt, references)
            task.progress = 76
            db.commit()
            result = render_and_slice(raw, plan.plan, settings.generated_dir / project.id / task.id)
            record.status = "SUCCEEDED"
            record.duration_ms = int((time.monotonic() - started) * 1000)
            task.status = TaskStatus.SUCCEEDED
            task.progress = 100
            task.result = {**result, "provider": candidate, "model": record.model, "design_plan_id": plan.id}
            project.status = ProjectStatus.GENERATED
            db.commit()
            return
        except (ImageGenerationError, httpx.HTTPError, OSError, ValueError) as exc:
            code = exc.code if isinstance(exc, ImageGenerationError) else "GENERATION_ERROR"
            record.status = "FAILED"
            record.error_code = code
            record.duration_ms = int((time.monotonic() - started) * 1000)
            errors.append(f"{candidate}:{exc}")
            db.commit()
    task.status = TaskStatus.FAILED_FINAL
    task.error_code = "ALL_PROVIDERS_FAILED"
    task.error_message = "；".join(errors)
    project.status = ProjectStatus.DESIGN_PLAN_CONFIRMED
    db.commit()
