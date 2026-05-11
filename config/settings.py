from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-32-chars-minimum-secret"
    debug: bool = False

    # FastAPI
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://jobbot:jobbot_password@localhost:5432/jobbot"
    database_url_sync: str = "postgresql://jobbot:jobbot_password@localhost:5432/jobbot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "jobbot-tasks"

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_multimodal_model: str = "qwen2.5vl:7b"
    ollama_text_model: str = "qwen2.5:7b"
    ollama_timeout: int = 8

    # AI Cloud
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # AI Routing
    ai_confidence_threshold: float = 0.75
    ai_local_first: bool = True

    # Storage
    storage_backend: str = "local"
    storage_local_path: str = "storage"
    # Screenshot persistence (set SAVE_SCREENSHOTS=true to store files on disk)
    save_screenshots: bool = False
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = "jobbot-files"
    aws_region: str = "us-east-1"

    # Encryption
    vault_encryption_key: str = "change-me-32-byte-fernet-key-here"

    # Browser
    browser_headless: bool = True
    browser_timeout: int = 30000
    browser_stealth: bool = True

    # Logging
    log_format: str = "json"

    # Resume
    latex_engine: str = "tectonic"


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
