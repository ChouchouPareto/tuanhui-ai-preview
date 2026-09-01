import hashlib
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from app.core.config import settings


ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


def store_upload(project_id: str, asset_id: str, upload: UploadFile) -> dict:
    if upload.content_type not in ALLOWED_MIME:
        raise ValueError("仅支持JPG、PNG或WEBP图片")
    content = upload.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"单张图片不能超过{settings.max_upload_mb}MB")
    digest = hashlib.sha256(content).hexdigest()
    target = settings.upload_dir / project_id / asset_id / "original"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    try:
        with Image.open(target) as image:
            image.verify()
        with Image.open(target) as image:
            width, height = image.size
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise ValueError("文件内容不是有效图片") from exc
    quality = {
        "resolution_ok": width >= 800 and height >= 600,
        "warnings": [] if width >= 800 and height >= 600 else ["图片分辨率偏低，建议补传更清晰图片"],
    }
    return {"path": str(target), "sha256": digest, "size": len(content), "width": width, "height": height, "quality": quality}

