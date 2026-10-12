from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    database_path: Path = BACKEND_DIR / "chatbot.db"
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    cookie_secure: bool = False
    session_days: int = Field(default=7, ge=1, le=30)
