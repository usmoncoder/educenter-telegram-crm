"""Environment-based configuration.

Only infrastructure-level and secret values live here. Business settings that administrators
edit at runtime (welcome text, SLA timeout, ...) live in the database (see services/app_settings.py).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: `TELEGRAM_API_ID=` in .env means "not set", not an invalid empty value.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    # Database (SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pass@host:5432/db)
    database_url: SecretStr = SecretStr("postgresql+asyncpg://educenter:educenter@localhost:5432/educenter")
    db_pool_size: int = 10
    db_max_overflow: int = 5

    # Web/API security
    # Comma-separated list (NoDecode: parsed by the validator below, not as JSON).
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    session_cookie_name: str = "educrm_session"
    session_ttl_hours: int = 12
    cookie_secure: bool | None = None  # defaults to True in production
    trusted_proxy_count: int = 0  # number of reverse proxies in front of the API (X-Forwarded-For hops)

    # Telegram (MTProto user account). Never exposed to the frontend.
    telegram_api_id: int | None = None
    telegram_api_hash: SecretStr | None = None
    telegram_phone: str | None = None
    telegram_session_dir: Path = Path("./data/session")
    telegram_session_name: str = "educenter"
    telegram_device_model: str = "EduCenter CRM"

    # Optional Bot API token used only for administrator alerts when alert channel is "bot".
    alert_bot_token: SecretStr | None = None

    # Worker tuning
    worker_tick_seconds: float = 5.0
    worker_heartbeat_seconds: float = 15.0
    worker_stale_after_seconds: int = 60

    display_timezone: str = "Asia/Tashkent"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.cookie_secure is None:
            self.cookie_secure = self.environment == "production"
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS='*' is not allowed in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_api_id and self.telegram_api_hash)

    @property
    def session_path(self) -> Path:
        return self.telegram_session_dir / self.telegram_session_name


@lru_cache
def get_settings() -> Settings:
    return Settings()
