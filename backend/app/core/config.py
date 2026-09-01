from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/tuanhui.db"
    upload_dir: Path = Path("./data/uploads")
    analyzer_mode: str = "mock"
    max_upload_mb: int = 15
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3011,http://127.0.0.1:3011"
    dashscope_api_key: str = ""
    bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_ocr_model: str = "qwen-vl-ocr-2025-11-20"
    bailian_vision_model: str = "qwen3-vl-plus"
    qwen_image_base_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    qwen_image_model: str = "qwen-image-3.0"
    ark_api_key: str = ""
    ark_image_base_url: str = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    doubao_image_model: str = "doubao-seedream-5-0-260128"
    generated_dir: Path = Path("./data/generated")
    model_timeout_seconds: int = 60

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


settings = Settings()
