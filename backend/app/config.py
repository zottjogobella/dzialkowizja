from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
    )

    # App
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    frontend_url: str = "http://localhost:5173"

    # App Database (own PostgreSQL)
    database_url: str = "postgresql+psycopg://dzialkowizja:dzialkowizja_dev@localhost:5433/dzialkowizja"
    database_url_sync: str = "postgresql://dzialkowizja:dzialkowizja_dev@localhost:5433/dzialkowizja"

    # Geo Database (gruntomat - read only)
    geo_db_host: str = "145.239.2.73"
    geo_db_port: int = 5432
    geo_db_name: str = "gruntomat"
    geo_db_user: str = ""
    geo_db_password: str = ""

    # Przetargi DB (real estate listings - read only)
    przetargi_db_host: str = "51.75.55.212"
    przetargi_db_port: int = 5432
    przetargi_db_name: str = "przetargi"
    przetargi_db_user: str = ""
    przetargi_db_password: str = ""

    # Transakcje DB (land transactions - read only)
    transakcje_db_host: str = "localhost"
    transakcje_db_port: int = 5432
    transakcje_db_name: str = "transakcje"
    transakcje_db_user: str = "deploy"
    transakcje_db_password: str = "deploy"

    # Google
    google_api_key: str = ""

    # Buffer distances (meters)
    buildings_buffer_m: int = 300
    listings_radius_m: int = 500

    # Snapshot generation
    snapshot_width: int = 600
    snapshot_height: int = 800
    snapshot_bbox_padding: float = 0.6
    snapshot_max_age_days: int = 30

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
