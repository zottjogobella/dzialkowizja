from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    frontend_url: str = "http://localhost:5173"

    # App Database (own PostgreSQL)
    database_url: str = "postgresql+asyncpg://dzialkowizja:dzialkowizja_dev@localhost:5433/dzialkowizja"
    database_url_sync: str = "postgresql://dzialkowizja:dzialkowizja_dev@localhost:5433/dzialkowizja"

    # Geo Database (gruntomat - read only)
    geo_db_host: str = "145.239.2.73"
    geo_db_port: int = 5432
    geo_db_name: str = "gruntomat"
    geo_db_user: str = ""
    geo_db_password: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""

    # Rate Limiting
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # Session
    session_max_age_seconds: int = 86400 * 7  # 7 days
    session_cookie_name: str = "dzialkowizja_session"
    session_secure_cookie: bool = False  # True in production

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def cors_origins(self) -> list[str]:
        if self.is_prod:
            return [self.frontend_url]
        return ["http://localhost:5173", "http://localhost:4173"]


settings = Settings()
