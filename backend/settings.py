from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    edo_lite_send_url: str = "https://edo-api.crpt.ru/api/v1/document"
    edo_lite_auth_token: str | None = None
    edo_lite_timeout_seconds: float = 20.0
    edo_lite_retry_attempts: int = 3
    edo_lite_retry_delay_seconds: float = 1.0
    national_catalog_send_url: str | None = None
    national_catalog_api_key: str | None = None
    national_catalog_supplier_key: str | None = None
    national_catalog_auth_token: str | None = None
    national_catalog_timeout_seconds: float = 20.0
    national_catalog_retry_attempts: int = 3
    national_catalog_retry_delay_seconds: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
