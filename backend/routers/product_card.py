"""Эндпоинты для карточек товаров Национального каталога."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from schemas import ProductCardCreate, ProductCardResponse
from services import product_card_service

router = APIRouter(prefix="/product-cards", tags=["National Catalog"])


@router.post("/", response_model=ProductCardResponse, status_code=status.HTTP_201_CREATED)
async def create_product_card(
    data: ProductCardCreate,
    db: AsyncSession = Depends(get_db_session),
) -> ProductCardResponse:
    return await product_card_service.create_card(data, db)


@router.get("/", response_model=list[ProductCardResponse])
async def list_product_cards(
    db: AsyncSession = Depends(get_db_session),
) -> list[ProductCardResponse]:
    return await product_card_service.get_cards(db)


@router.get("/{card_id}", response_model=ProductCardResponse)
async def get_product_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ProductCardResponse:
    card = await product_card_service.get_card(card_id, db)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карточка товара не найдена")
    return card


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await product_card_service.delete_card(card_id, db)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карточка товара не найдена")


@router.post("/{card_id}/copy", response_model=ProductCardResponse, status_code=status.HTTP_201_CREATED)
async def copy_product_card(
    card_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ProductCardResponse:
    card = await product_card_service.create_similar_card(card_id, db)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карточка товара не найдена")
    return card


@router.post("/{card_id}/sync-feed-status", response_model=ProductCardResponse)
async def sync_product_card_feed_status(
    card_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ProductCardResponse:
    return await product_card_service.sync_card_feed_status(card_id, db)
