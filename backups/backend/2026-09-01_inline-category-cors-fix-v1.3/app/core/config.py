from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/tuanhui.db"
    upload_dir: Path = Path("./data/uploads")
    analyzer_mode: str = "mock"
    max_upload_mb: int = 15
    allowed_origins: str = "http://localhost:3000"
    dashscope_api_key: str = ""
    bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_ocr_model: str = "qwen-vl-ocr-2025-11-20"
    bailian_vision_model: str = "qwen3-vl-plus"
    model_timeout_seconds: int = 60

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


settings = Settings()
