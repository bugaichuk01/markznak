"""SQLAlchemy ORM models (async engine; metadata on ``database.Base``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


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
    CREATED = "created"      # локальный черновик
    PENDING = "pending"      # В обработке (СУЗ обрабатывает)
    AVAILABLE = "available"  # Готов — можно скачать КМ
    EXHAUSTED = "exhausted"  # Не содержит больше кодов (скачан)
    CLOSED = "closed"        # Закрыт (после close API)
    REJECTED = "rejected"    # Отклонён / ошибка


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class Device(Base):
    """Настройки подключения к Честному Знаку (имя устройства, OMS, соединение)."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    oms_id: Mapped[str] = mapped_column(String(255), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(512), nullable=False)
    inn: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OrganizationSettings(Base):
    """Организационные настройки (в т.ч. номер МЧД)."""

    __tablename__ = "organization_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    mchd_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OzonMapping(Base):
    """Связка GTIN ↔ данные товара и OZON ID для автоподстановки при отгрузке."""

    __tablename__ = "ozon_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    gtin: Mapped[str] = mapped_column(String(14), nullable=False, unique=True, index=True)
    article: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    ozon_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DocumentUPD(Base):
    """УПД на отгрузку: коды маркировки, тип ЭДО, статус, черновик XML для коммерческого ЭДО."""

    __tablename__ = "document_upds"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_number: Mapped[str] = mapped_column(String(128), nullable=False)
    marking_codes: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: [],
    )
    disable_owner_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edo_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    xml_draft_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_thumbprint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    signature_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    seller_inn: Mapped[str | None] = mapped_column(String(12), nullable=True)
    seller_kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    seller_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    buyer_inn: Mapped[str | None] = mapped_column(String(12), nullable=True)
    buyer_kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    buyer_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SuzToken(Base):
    """Хранение clientToken СУЗ с временем истечения."""

    __tablename__ = "suz_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    oms_connection_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    true_api_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    true_api_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProductCard(Base):
    """Карточка товара Национального каталога."""

    __tablename__ = "product_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    type: Mapped[ProductCardType] = mapped_column(
        Enum(
            ProductCardType,
            name="product_card_type",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    tn_ved: Mapped[str] = mapped_column(String(32), nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[ProductCardStatus] = mapped_column(
        Enum(
            ProductCardStatus,
            name="product_card_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ProductCardStatus.DRAFT,
    )
    national_catalog_feed_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    national_catalog_feed_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    national_catalog_feed_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(256), nullable=True)
    color: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    composition: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_kind: Mapped[str | None] = mapped_column(String(128), nullable=True)
    regulation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    tn_ved_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tn_ved_group: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_article_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_article: Mapped[str | None] = mapped_column(String(256), nullable=True)
    custom_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra_attrs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class EmissionOrder(Base):
    """Заказ на эмиссию кодов в СУЗ."""

    __tablename__ = "emission_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    product_card_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_cards.id", ondelete="CASCADE"),
        nullable=True,
    )
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[EmissionOrderStatus] = mapped_column(
        Enum(
            EmissionOrderStatus,
            name="emission_order_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=EmissionOrderStatus.CREATED,
    )
    suz_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    suz_marking_codes: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: [],
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class GtinExtraFields(Base):
    """Дополнительные поля к GTIN для печати этикеток и УПД."""

    __tablename__ = "gtin_extra_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    gtin: Mapped[str] = mapped_column(String(14), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str | None] = mapped_column(String(128), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(256), nullable=True)
    composition: Mapped[str | None] = mapped_column(String(512), nullable=True)
    edo_inn: Mapped[str | None] = mapped_column(String(12), nullable=True)
    edo_kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    edo_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UtilisationStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ERROR = "error"


class UtilisationReport(Base):
    """Отчёт о нанесении КМ (ввод в оборот)."""

    __tablename__ = "utilisation_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    product_group: Mapped[str] = mapped_column(String(64), nullable=False, default="perfumery")
    marking_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[UtilisationStatus] = mapped_column(
        Enum(UtilisationStatus, name="utilisation_status", values_callable=_enum_values),
        nullable=False,
        default=UtilisationStatus.DRAFT,
    )
    report_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WithdrawalStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ERROR = "error"


class WithdrawalReport(Base):
    """Отчёт о выводе КМ из оборота."""

    __tablename__ = "withdrawal_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    withdrawal_type: Mapped[str] = mapped_column(String(64), nullable=False, default="SOLD")
    product_group: Mapped[str] = mapped_column(String(64), nullable=False, default="perfumery")
    marking_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus, name="withdrawal_status", values_callable=_enum_values),
        nullable=False,
        default=WithdrawalStatus.DRAFT,
    )
    document_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LabelTemplate(Base):
    """Шаблон этикетки для печати кодов маркировки."""

    __tablename__ = "label_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    layout_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
