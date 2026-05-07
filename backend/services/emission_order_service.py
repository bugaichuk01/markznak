"""Бизнес-логика заказов на эмиссию кодов (СУЗ)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import EmissionOrder, EmissionOrderStatus, ProductCard
from schemas import EmissionOrderCreate


async def create_order(data: EmissionOrderCreate, db: AsyncSession) -> EmissionOrder:
    product_card = await db.get(ProductCard, data.product_card_id)
    if product_card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карточка товара не найдена")

    order = EmissionOrder(
        product_card_id=data.product_card_id,
        quantity=data.quantity,
        status=EmissionOrderStatus.CREATED,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def get_orders(db: AsyncSession) -> list[EmissionOrder]:
    result = await db.scalars(select(EmissionOrder).order_by(EmissionOrder.created_at.desc()))
    return list(result.all())


async def update_order_status(order_id: UUID, status_value: str, db: AsyncSession) -> EmissionOrder:
    order = await db.get(EmissionOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Заказ на эмиссию не найден")

    try:
        next_status = EmissionOrderStatus(status_value)
    except ValueError as exc:
        allowed_statuses = ", ".join(s.value for s in EmissionOrderStatus)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Некорректный статус. Допустимые значения: {allowed_statuses}",
        ) from exc

    order.status = next_status
    await db.commit()
    await db.refresh(order)
    return order


async def merge_orders(order_ids: list[UUID], db: AsyncSession) -> EmissionOrder:
    unique_order_ids = list(dict.fromkeys(order_ids))
    if len(unique_order_ids) < 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Для объединения необходимо минимум два разных заказа",
        )

    result = await db.scalars(select(EmissionOrder).where(EmissionOrder.id.in_(unique_order_ids)))
    orders = list(result.all())
    if len(orders) != len(unique_order_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Один или несколько заказов не найдены")

    first_product_card_id = orders[0].product_card_id
    if any(order.product_card_id != first_product_card_id for order in orders):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Нельзя объединить заказы разных карточек товара",
        )

    if any(order.status != EmissionOrderStatus.CREATED for order in orders):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Объединять можно только заказы со статусом created",
        )

    merged_order = EmissionOrder(
        product_card_id=first_product_card_id,
        quantity=sum(order.quantity for order in orders),
        status=EmissionOrderStatus.CREATED,
    )
    db.add(merged_order)

    for order in orders:
        await db.delete(order)

    await db.commit()
    await db.refresh(merged_order)
    return merged_order
