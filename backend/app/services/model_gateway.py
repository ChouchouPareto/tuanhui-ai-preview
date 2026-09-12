import base64
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.schemas import OCRPayload, VisualFactPayload


class ModelGatewayError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.safe_message = message


def load_prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8").strip()


def parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(candidate):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(candidate[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ModelGatewayError("MODEL_BAD_OUTPUT", "模型返回格式不符合要求")


def _image_data_url(path: str, mime_type: str) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _post_chat(model: str, messages: list[dict]) -> tuple[str, dict, int]:
    if not settings.dashscope_api_key.strip():
        raise ModelGatewayError("MODEL_CONFIG_MISSING", "尚未配置百炼API Key")
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{settings.bailian_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.dashscope_api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0},
            timeout=settings.model_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise ModelGatewayError("MODEL_TIMEOUT", "模型请求超时，请稍后重试") from exc
    except httpx.HTTPError as exc:
        raise ModelGatewayError("MODEL_UPSTREAM_ERROR", "模型服务暂时不可用") from exc
    duration_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code in {401, 403}:
        raise ModelGatewayError("MODEL_AUTH_FAILED", "百炼认证失败，请检查Key与Base URL")
    if response.status_code == 429:
        raise ModelGatewayError("MODEL_RATE_LIMITED", "模型调用频率受限，请稍后重试")
    if response.status_code >= 400:
        raise ModelGatewayError("MODEL_UPSTREAM_ERROR", "模型服务返回错误")
    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelGatewayError("MODEL_BAD_OUTPUT", "模型响应结构不符合要求") from exc
    return str(content), payload.get("usage") or {}, duration_ms


def recognize_image(path: str, mime_type: str, asset_type: str = "menu") -> tuple[OCRPayload, dict]:
    prompt_name = "storefront_ocr.txt" if asset_type in {"storefront", "environment"} else "menu_ocr.txt"
    model = settings.bailian_vision_model if asset_type in {"storefront", "environment"} else settings.bailian_ocr_model
    text, usage, duration_ms = _post_chat(
        model,
        [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _image_data_url(path, mime_type)}},
                {"type": "text", "text": load_prompt(prompt_name) + ("\n本图为店内环境：没有清晰招牌时不要推测店名，重点提取色彩、材质、风格与可见文字线索。" if asset_type == "environment" else "")},
            ],
        }],
    )
    try:
        result = OCRPayload.model_validate(parse_json_object(text))
    except Exception as exc:
        if isinstance(exc, ModelGatewayError):
            raise
        raise ModelGatewayError("MODEL_BAD_OUTPUT", "OCR结果未通过结构校验") from exc
    return result, {"model": model, "usage": usage, "duration_ms": duration_ms}


def infer_store_facts(project_name: str, ocr_items: list[dict]) -> tuple[VisualFactPayload, dict]:
    evidence = json.dumps({"project_name": project_name, "ocr_results": ocr_items}, ensure_ascii=False)
    text, usage, duration_ms = _post_chat(
        settings.bailian_vision_model,
        [
            {"role": "system", "content": load_prompt("store_facts.txt")},
            {"role": "user", "content": evidence},
        ],
    )
    try:
        result = VisualFactPayload.model_validate(parse_json_object(text))
    except Exception as exc:
        if isinstance(exc, ModelGatewayError):
            raise
        raise ModelGatewayError("MODEL_BAD_OUTPUT", "门店事实结果未通过结构校验") from exc
    return result, {"model": settings.bailian_vision_model, "usage": usage, "duration_ms": duration_ms}
