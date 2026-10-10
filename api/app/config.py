"""Application settings - typed, loaded from the environment (api/.env locally)"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[1]  # api/


class Settings(BaseSettings):
    """Every env var the API understands (see api/.env.example)."""

    model_config = SettingsConfigDict(
        env_file=API_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- database (required - fails fast when missing) ---
    database_url: str = ""

    # --- chat provider: openai | deepseek ---
    chat_provider: Literal["openai", "deepseek"] = "openai"
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-5-mini"
    deepseek_api_key: str | None = None
    deepseek_chat_model: str = "deepseek-chat"

    # --- embedding ---
    embedding_model: str = "text-embedding-3-small"

    # --- web + uploads ---
    web_origin: str = "http://localhost:3000"
    max_upload_mb: int = 20

    @field_validator("database_url")
    @classmethod
    def _require_database_url(cls, value: str) -> str:
        """Reject missing/empty DATABASE_URL early with a clear message"""

        if not value:
            raise ValueError("DATABASE_URL is required (set it in api/.env or the environment)")
        return value


settings = Settings()
