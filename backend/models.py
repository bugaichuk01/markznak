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
    CREATED = "created"
    PENDING = "pending"
    AVAILABLE = "available"
    REJECTED = "rejected"


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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
