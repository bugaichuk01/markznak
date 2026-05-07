"""Бизнес-логика и CRUD-операции для карточек товаров Национального каталога."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from models import ProductCard, ProductCardStatus
from schemas import ProductCardCreate
from services.national_catalog_integration_service import (
    NationalCatalogIntegrationError,
    fetch_feed_status,
    send_product_card,
)

_FEED_STATUS_TO_CARD_STATUS: dict[str, ProductCardStatus] = {
    "Signed": ProductCardStatus.PUBLISHED,
    "Moderated": ProductCardStatus.SENT,
    "Processing": ProductCardStatus.SENT,
    "Received": ProductCardStatus.SENT,
    "Rejected": ProductCardStatus.DRAFT,
}


async def create_card(data: ProductCardCreate, db: AsyncSession) -> ProductCard:
    card = ProductCard(
        type=data.type,
        tn_ved=data.tn_ved.strip(),
        gtin=data.gtin.strip() if data.gtin else None,
        name=data.name.strip(),
        status=ProductCardStatus.DRAFT,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)

    try:
        submission_result = await send_product_card(card, data.cat_id)
    except NationalCatalogIntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Карточка создана локально, но не отправлена в Национальный каталог: {exc}",
        ) from exc

    card.national_catalog_feed_id = submission_result.feed_id
    card.national_catalog_feed_status = submission_result.feed_status
    card.national_catalog_feed_payload = submission_result.feed_payload
    card.status = _FEED_STATUS_TO_CARD_STATUS.get(
        submission_result.feed_status or "",
        ProductCardStatus.PUBLISHED
        if submission_result.remote_status == ProductCardStatus.PUBLISHED.value
        else ProductCardStatus.SENT,
    )
    await db.commit()
    await db.refresh(card)
    return card


async def get_cards(db: AsyncSession) -> list[ProductCard]:
    result = await db.scalars(select(ProductCard).order_by(ProductCard.created_at.desc()))
    return list(result.all())


async def get_card(card_id: UUID, db: AsyncSession) -> ProductCard | None:
    return await db.get(ProductCard, card_id)


async def delete_card(card_id: UUID, db: AsyncSession) -> bool:
    card = await db.get(ProductCard, card_id)
    if card is None:
        return False
    await db.delete(card)
    await db.commit()
    return True


async def create_similar_card(card_id: UUID, db: AsyncSession) -> ProductCard | None:
    source_card = await db.get(ProductCard, card_id)
    if source_card is None:
        return None

    copied_card = ProductCard(
        type=source_card.type,
        tn_ved=source_card.tn_ved,
        gtin=source_card.gtin,
        name=f"(Копия) {source_card.name}",
        status=ProductCardStatus.DRAFT,
    )
    db.add(copied_card)
    await db.commit()
    await db.refresh(copied_card)
    return copied_card


async def sync_card_feed_status(card_id: UUID, db: AsyncSession) -> ProductCard:
    card = await db.get(ProductCard, card_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карточка товара не найдена")
    if not card.national_catalog_feed_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Для карточки отсутствует feed_id. Сначала отправьте карточку в Национальный каталог.",
        )

    from settings import get_settings

    settings = get_settings()
    headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    auth_params: dict[str, str] = {}
    if settings.national_catalog_api_key:
        auth_params["apikey"] = settings.national_catalog_api_key
    elif settings.national_catalog_auth_token:
        headers["Authorization"] = f"Bearer {settings.national_catalog_auth_token}"
    else:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не настроена авторизация НК (NATIONAL_CATALOG_API_KEY/NATIONAL_CATALOG_AUTH_TOKEN).",
        )

    feed_status, feed_payload = await fetch_feed_status(
        feed_id=card.national_catalog_feed_id,
        settings_send_url=settings.national_catalog_send_url,
        auth_params=auth_params,
        headers=headers,
        supplier_key=settings.national_catalog_supplier_key,
        timeout_seconds=settings.national_catalog_timeout_seconds,
    )
    card.national_catalog_feed_status = feed_status
    card.national_catalog_feed_payload = feed_payload
    if feed_status in _FEED_STATUS_TO_CARD_STATUS:
        card.status = _FEED_STATUS_TO_CARD_STATUS[feed_status]
    await db.commit()
    await db.refresh(card)
    return card
