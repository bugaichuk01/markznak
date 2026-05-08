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

    # СУЗ / OMS API v2 (список заказов; URL и токен — из руководства к вашему контуру СУЗ)
    suz_api_base_url: str | None = None
    # Legacy clientToken (v2) / fallback when SUZ_AUTH_TOKEN is not provided.
    suz_client_token: str | None = None
    # Bearer token (v3 security marker/access token) for Authorization header.
    suz_auth_token: str | None = None
    suz_oms_id: str | None = None
    # Connection ID из ЛК СУЗ (для регистрации устройства / подсказки в UI; не путать с clientToken).
    suz_connection_id: str | None = None
    suz_product_group: str = "perfum"
    suz_timeout_seconds: float = 30.0
    # TLS: в песочнице часто нужно SUZ_TLS_VERIFY=false (без проверки сертификата — только тест/stage).
    suz_tls_verify: bool = False
    suz_ssl_compat: bool = True
    suz_curl_fallback: bool = True
    # Тело POST /api/v2/{grp}/orders?omsId=... (OMS v2 ЦРПТ; см. инструкцию к контуру для enum-значений).
    suz_order_contact_person: str = "integration@localhost"
    suz_order_release_method_type: str = "REMARK_PRODUCTION_RU"
    suz_order_create_method_type: str = "SELF_MADE"
    suz_serial_number_type: str = "OPERATOR"
    suz_marking_template_id: int = 1
    # Только для perfume / lp и аналогичных продуктовых групп с полем cisType в SKU.
    suz_product_cis_type: str = "UNIT"
    # Только группа «свет»: contractNumber и contractDate (строка YYYY-MM-DD).
    suz_order_contract_number: str = "SANDBOX-CONTRACT"
    suz_order_contract_date: str = "2026-01-01"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
