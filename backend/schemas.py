"""Pydantic-схемы для API (Create / Update / Response)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EdoType(StrEnum):
    """Тип электронного документооборота для УПД."""

    EDO_LITE = "edo_lite"
    COMMERCIAL_EDO = "commercial_edo"


class DocumentStatus(StrEnum):
    """Статус жизненного цикла УПД."""

    DRAFT = "draft"
    SIGNED = "signed"
    SENT = "sent"


class SignatureFormat(StrEnum):
    """Поддерживаемый формат электронной подписи."""

    DETACHED_CMS_BASE64 = "detached_cms_base64"


class ProductCardType(StrEnum):
    UNIT = "unit"
    SET = "set"
    TECH_CARD = "tech_card"
    BUNDLE = "bundle"


class ProductCardStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PUBLISHED = "published"


class EmissionOrderStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    AVAILABLE = "available"
    REJECTED = "rejected"


# --- Device ---


class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    oms_id: str = Field(..., min_length=1, max_length=255)
    connection_id: str = Field(..., min_length=1, max_length=512)


class DeviceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    oms_id: str | None = Field(None, min_length=1, max_length=255)
    connection_id: str | None = Field(None, min_length=1, max_length=512)


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    oms_id: str
    connection_id: str
    created_at: datetime


class DeviceFormDefaultsResponse(BaseModel):
    """Значения из .env (SUZ_OMS_ID / SUZ_CONNECTION_ID) для подстановки в форму устройства."""

    oms_id: str | None = None
    connection_id: str | None = None


# --- OrganizationSettings ---


class OrganizationSettingsCreate(BaseModel):
    mchd_number: str | None = Field(None, max_length=128)


class OrganizationSettingsUpdate(BaseModel):
    mchd_number: str | None = Field(None, max_length=128)


class OrganizationSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mchd_number: str | None
    updated_at: datetime


# --- OzonMapping ---


class OzonMappingCreate(BaseModel):
    gtin: str = Field(..., min_length=8, max_length=14)
    article: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=512)
    ozon_id: str = Field(..., min_length=1, max_length=64)


class OzonMappingUpdate(BaseModel):
    gtin: str | None = Field(None, min_length=8, max_length=14)
    article: str | None = Field(None, min_length=1, max_length=255)
    name: str | None = Field(None, min_length=1, max_length=512)
    ozon_id: str | None = Field(None, min_length=1, max_length=64)


class OzonMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gtin: str
    article: str
    name: str
    ozon_id: str
    created_at: datetime


# --- DocumentUPD ---


class DocumentUPDCreate(BaseModel):
    document_number: str = Field(..., min_length=1, max_length=128)
    marking_codes: list[str] = Field(default_factory=list)
    disable_owner_control: bool = False
    edo_type: EdoType
    status: DocumentStatus = DocumentStatus.DRAFT
    xml_draft_content: str | None = None


class DocumentUPDUpdate(BaseModel):
    document_number: str | None = Field(None, min_length=1, max_length=128)
    marking_codes: list[str] | None = None
    disable_owner_control: bool | None = None
    edo_type: EdoType | None = None
    status: DocumentStatus | None = None
    xml_draft_content: str | None = None


class DocumentUPDResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_number: str
    marking_codes: list[str]
    disable_owner_control: bool
    edo_type: EdoType
    status: DocumentStatus
    xml_draft_content: str | None
    signature_format: SignatureFormat | None
    signature_thumbprint: str | None
    signature_metadata: dict[str, Any] | None
    signed_at: datetime | None
    sent_at: datetime | None
    external_message_id: str | None
    external_status: str | None
    created_at: datetime


# --- ProductCard ---


class ProductCardCreate(BaseModel):
    type: ProductCardType
    tn_ved: str = Field(..., min_length=1, max_length=32)
    gtin: str | None = Field(None, min_length=8, max_length=14)
    cat_id: int | None = Field(None, gt=0)
    name: str = Field(..., min_length=1, max_length=512)
    status: ProductCardStatus = ProductCardStatus.DRAFT

    @model_validator(mode="after")
    def validate_business_rules(self) -> "ProductCardCreate":
        if self.type == ProductCardType.BUNDLE:
            raise ValueError(
                "Карточки с типом Набор создаются и редактируются только через сайт Честного Знака"
            )
        if self.type in {ProductCardType.UNIT, ProductCardType.SET} and not self.gtin:
            raise ValueError("Для типов Единица и Комплект требуется GTIN (регистрация в ГС1 РУС)")
        if not self.tn_ved.strip().isdigit():
            raise ValueError("ТН ВЭД должен содержать только цифры")
        return self


class ProductCardUpdate(BaseModel):
    type: ProductCardType | None = None
    tn_ved: str | None = Field(None, min_length=1, max_length=32)
    gtin: str | None = Field(None, min_length=8, max_length=14)
    name: str | None = Field(None, min_length=1, max_length=512)
    status: ProductCardStatus | None = None

    @model_validator(mode="after")
    def validate_bundle_edit(self) -> "ProductCardUpdate":
        if self.type == ProductCardType.BUNDLE:
            raise ValueError(
                "Карточки с типом Набор создаются и редактируются только через сайт Честного Знака"
            )
        return self


class ProductCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: ProductCardType
    tn_ved: str
    gtin: str | None
    name: str
    status: ProductCardStatus
    national_catalog_feed_id: str | None
    national_catalog_feed_status: str | None
    national_catalog_feed_payload: dict[str, Any] | None
    created_at: datetime


# --- EmissionOrder ---


class EmissionOrderCreate(BaseModel):
    product_card_id: UUID
    quantity: int = Field(..., gt=0)
    status: EmissionOrderStatus = EmissionOrderStatus.CREATED
    suz_order_id: str | None = Field(None, min_length=1, max_length=128)
    # Для техкарточек без GTIN: подставить код для отправки заказа в СУЗ (OMS требует gtin в теле заказа).
    gtin: str | None = Field(None, min_length=8, max_length=14)

    @field_validator("gtin", mode="before")
    @classmethod
    def _strip_optional_gtin(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("gtin")
    @classmethod
    def _digits_gtin_order(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not str(v).isdigit():
            raise ValueError("GTIN должен содержать только цифры")
        return v


class EmissionOrderGtinPatch(BaseModel):
    """Установка GTIN у локального заказа (например, карточка — техбез gtin)."""

    gtin: str = Field(..., min_length=8, max_length=14)

    @field_validator("gtin")
    @classmethod
    def _digits_only(cls, v: str) -> str:
        s = v.strip()
        if not s.isdigit():
            raise ValueError("GTIN должен содержать только цифры")
        return s


class EmissionOrderUpdate(BaseModel):
    product_card_id: UUID | None = None
    quantity: int | None = Field(None, gt=0)
    status: EmissionOrderStatus | None = None
    suz_order_id: str | None = Field(None, min_length=1, max_length=128)


class EmissionOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_card_id: UUID | None
    gtin: str | None
    quantity: int
    status: EmissionOrderStatus
    suz_order_id: str | None
    suz_marking_codes: list[str] = Field(default_factory=list)
    created_at: datetime


class MarkingCodePrintOptionsResponse(BaseModel):
    """Коды для печати этикеток: из ответов СУЗ (при синхронизации) и из УПД."""

    codes: list[str]


class EmissionOrderStatusUpdateRequest(BaseModel):
    status: EmissionOrderStatus


class MergeOrdersRequest(BaseModel):
    order_ids: list[UUID] = Field(..., min_length=2)


class SuzSyncResponse(BaseModel):
    inserted: int
    updated: int
    total_remote: int


class SuzSendOrderPayload(BaseModel):
    """Подробности ответа СУЗ при создании заказа (camelCase сохранён для отладки)."""

    remote_order_id: str
    payload: dict[str, Any]


class SuzSendOrderResponse(BaseModel):
    """Результат «Отправить в СУЗ»: обновлённый локальный заказ + краткая сводка ответа удалённой стороны."""

    emission_order: EmissionOrderResponse
    suz: SuzSendOrderPayload


class SuzConnectivityDiagnosticsResponse(BaseModel):
    """Диагностика TLS/DNS/curl до OMS без реального clientToken (фиктивный токен в запросе)."""

    heuristic_hints: list[str]
    suggested_base_url_when_nk_crptech_sandbox: str | None
    probes: list[dict[str, Any]]
    verdict: str
    docs_pointer: str


# --- LabelTemplate ---


class LabelTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    layout_data: dict[str, Any] = Field(default_factory=dict)


class LabelTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    width: int | None = Field(None, gt=0)
    height: int | None = Field(None, gt=0)
    layout_data: dict[str, Any] | None = None


class LabelTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    width: int
    height: int
    layout_data: dict[str, Any]


# --- Ozon XML / Excel ---


class OzonParsedProduct(BaseModel):
    """Товар после разбора XML Ozon (OZON ID подставляется из OzonMapping при наличии)."""

    article: str
    name: str
    price_vat: str | None = Field(None, description="Цена/НДС одной строкой, если есть в файле")
    gtin: str
    ozon_id: str | None = None


class OzonParseXmlResponse(BaseModel):
    products: list[OzonParsedProduct]


class ExcelTemplateProduct(BaseModel):
    """Строка для генерации шаблона Excel."""

    article: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=512)
    gtin: str = Field(..., min_length=8, max_length=14)
    ozon_id: str | None = Field(None, max_length=64)


class ExcelTemplateRequest(BaseModel):
    items: list[ExcelTemplateProduct] = Field(default_factory=list)


class ExcelImportResult(BaseModel):
    """Результат импорта связок GTIN ↔ OZON ID."""

    created: int
    updated: int
    skipped: int


# --- УПД (создание через API) ---


class UpdCreateRequest(BaseModel):
    """Тело запроса на создание УПД; статус и XML задаёт сервер."""

    document_number: str = Field(..., min_length=1, max_length=128)
    marking_codes: list[str] = Field(default_factory=list)
    disable_owner_control: bool = False
    edo_type: EdoType


class UpdSendRequest(BaseModel):
    """Тело запроса на подписание/отправку УПД."""

    class SignaturePayload(BaseModel):
        format: SignatureFormat = SignatureFormat.DETACHED_CMS_BASE64
        value: str = Field(..., min_length=1)
        thumbprint: str | None = Field(None, min_length=1, max_length=256)
        signed_at: datetime | None = None
        metadata: dict[str, Any] = Field(default_factory=dict)

        @field_validator("value")
        @classmethod
        def validate_base64(cls, value: str) -> str:
            normalized = value.strip()
            if len(normalized) < 32:
                raise ValueError("Signature payload is too short")
            try:
                import base64

                base64.b64decode(normalized, validate=True)
            except Exception as exc:  # pragma: no cover - defensive validator
                raise ValueError("Signature value must be valid base64") from exc
            return normalized

    signature: SignaturePayload
