from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    google_api_key: str = ""
    gemini_api_key: str = ""
    gemini_orchestrator_key: str = ""
    gemini_worker_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    embedding_model: str = "gemini-embedding-001"
    worker_audit_model: str = "gemini-3.5-flash"
    database_url: str = ""
    database_path: Path = BACKEND_DIR / "chatbot.db"
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ]
    cookie_secure: bool = False
    session_days: int = Field(default=7, ge=1, le=30)

    @property
    def db_target(self) -> str | Path:
        """Returns PostgreSQL connection URL if provided, otherwise SQLite Path."""
        if self.database_url and (
            self.database_url.startswith("postgresql://")
            or self.database_url.startswith("postgres://")
        ):
            return self.database_url
        return self.database_path

    @property
    def orchestrator_keys(self) -> list[str]:
        """Candidate keys for Orchestrator chat with automatic failover."""
        if (
            "google_api_key" in self.model_fields_set
            and not self.google_api_key
            and "gemini_orchestrator_key" not in self.model_fields_set
        ):
            return []
        keys = []
        for k in [self.gemini_orchestrator_key, self.gemini_api_key, self.google_api_key, self.gemini_worker_key]:
            if k and k != "replace_with_your_google_ai_studio_key" and k not in keys:
                keys.append(k)
        return keys

    @property
    def worker_keys(self) -> list[str]:
        """Candidate keys for Worker embeddings/audits with automatic failover."""
        if (
            "google_api_key" in self.model_fields_set
            and not self.google_api_key
            and "gemini_worker_key" not in self.model_fields_set
        ):
            return []
        keys = []
        for k in [self.gemini_worker_key, self.gemini_api_key, self.google_api_key, self.gemini_orchestrator_key]:
            if k and k != "replace_with_your_google_ai_studio_key" and k not in keys:
                keys.append(k)
        return keys
