"""Бизнес-логика заказов на эмиссию кодов (СУЗ)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device, EmissionOrder, EmissionOrderStatus, ProductCard
from schemas import EmissionOrderCreate
from services.suz_integration_service import (
    SuzIntegrationError,
    build_suz_create_order_body,
    fetch_suz_orders_raw,
    map_suz_status_to_emission,
    submit_suz_emission_order,
)
from settings import get_settings

_SUZ_TRANSPORT_DIAG_HINT = (
    " Подробнее (TLS/DNS, без вашего clientToken): GET /api/v1/emission-orders/diagnostics/connectivity."
)


def _gtin_variants(raw: str | None) -> set[str]:
    if not raw:
        return set()
    digits = "".join(c for c in str(raw) if c.isdigit())
    if not digits:
        return set()
    out = {digits}
    if len(digits) <= 14:
        out.add(digits.zfill(14))
    stripped = digits.lstrip("0") or "0"
    out.add(stripped)
    if len(stripped) <= 14:
        out.add(stripped.zfill(14))
    return {x for x in out if x}


def _normalize_gtin14_for_suz(raw: str | None) -> str | None:
    """14-значный GTIN без изменения набора SKU (только дополнение нулями до 14)."""
    if not raw:
        return None
    digits = "".join(c for c in str(raw) if c.isdigit())
    if not digits:
        return None
    if len(digits) > 14:
        digits = digits[-14:]
    return digits.zfill(14)


async def _resolve_product_card_by_gtin(db: AsyncSession, gtin: str | None) -> ProductCard | None:
    variants = _gtin_variants(gtin)
    if not variants:
        return None
    result = await db.scalars(select(ProductCard).where(ProductCard.gtin.in_(variants)))
    cards = list(result.all())
    return cards[0] if cards else None


async def _resolve_oms_for_suz(db: AsyncSession) -> str:
    settings = get_settings()
    oms = (settings.suz_oms_id or "").strip()
    if not oms:
        dev_result = await db.scalars(select(Device).order_by(Device.created_at.asc()).limit(1))
        device = dev_result.first()
        if device:
            oms = device.oms_id.strip()
    return oms


async def create_order(data: EmissionOrderCreate, db: AsyncSession) -> EmissionOrder:
    product_card = await db.get(ProductCard, data.product_card_id)
    if product_card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карточка товара не найдена")

    from_override = _normalize_gtin14_for_suz(data.gtin.strip() if data.gtin else None)
    from_card = _normalize_gtin14_for_suz(product_card.gtin)
    order_gtin = from_override or from_card

    order = EmissionOrder(
        product_card_id=data.product_card_id,
        gtin=order_gtin,
        quantity=data.quantity,
        status=EmissionOrderStatus.CREATED,
        suz_order_id=data.suz_order_id,
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

    if any(o.product_card_id is None for o in orders):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Объединять можно только заказы с привязанной карточкой товара (подтяните GTIN или выберите карточку вручную).",
        )

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
        gtin=orders[0].gtin,
        quantity=sum(order.quantity for order in orders),
        status=EmissionOrderStatus.CREATED,
    )
    db.add(merged_order)

    for order in orders:
        await db.delete(order)

    await db.commit()
    await db.refresh(merged_order)
    return merged_order


async def sync_orders_from_suz(db: AsyncSession) -> dict[str, int]:
    """Подтягивает заказы из API СУЗ (OMS v2) и upsert в БД по suz_order_id."""
    oms = await _resolve_oms_for_suz(db)

    try:
        rows, _url = await fetch_suz_orders_raw(oms_id=oms if oms else None)
    except SuzIntegrationError as exc:
        hint = _SUZ_TRANSPORT_DIAG_HINT if exc.suggest_transport_diagnostics else ""
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"{exc}{hint}",
        ) from exc

    inserted = 0
    updated = 0
    for row in rows:
        suz_oid = row["order_id"]
        gtin: str | None = row.get("gtin")
        qty = int(row["quantity"])
        st = EmissionOrderStatus(map_suz_status_to_emission(row.get("status_raw") or ""))
        card = await _resolve_product_card_by_gtin(db, gtin)

        existing = await db.scalar(select(EmissionOrder).where(EmissionOrder.suz_order_id == suz_oid))
        if existing:
            existing.quantity = qty
            existing.status = st
            existing.gtin = gtin
            if card:
                existing.product_card_id = card.id
            updated += 1
        else:
            db.add(
                EmissionOrder(
                    product_card_id=card.id if card else None,
                    gtin=gtin,
                    quantity=qty,
                    status=st,
                    suz_order_id=suz_oid,
                )
            )
            inserted += 1

    await db.commit()
    return {"inserted": inserted, "updated": updated, "total_remote": len(rows)}


async def patch_order_gtin(order_id: UUID, gtin_plain: str, db: AsyncSession) -> EmissionOrder:
    """Подставляет GTIN в локальный заказ (актуально для техкарточек без GTIN в НК)."""
    order = await db.get(EmissionOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Заказ на эмиссию не найден")

    if order.suz_order_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Нельзя изменить GTIN после отправки заказа в СУЗ.",
        )
    if order.status != EmissionOrderStatus.CREATED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail='GTIN можно задать только для заказа со статусом «создан» (created).',
        )

    gtin14 = _normalize_gtin14_for_suz(gtin_plain.strip())
    if not gtin14:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Некорректный формат GTIN.")

    order.gtin = gtin14
    await db.commit()
    await db.refresh(order)
    return order


async def send_order_to_suz(order_id: UUID, db: AsyncSession) -> tuple[EmissionOrder, str, dict[str, Any]]:
    """Создаёт заказ эмиссии в СУЗ (POST OMS API v2), сохраняет suz_order_id и переводит в pending."""
    order = await db.get(EmissionOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Заказ на эмиссию не найден")

    if order.suz_order_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Заказ уже связан с СУЗ (указан идентификатор удалённого заказа).",
        )
    if order.status != EmissionOrderStatus.CREATED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail='Отправить в СУЗ можно только заказ со статусом «создан» (created).',
        )

    gtin_raw: str | None = order.gtin.strip() if (order.gtin and str(order.gtin).strip()) else None
    if not gtin_raw and order.product_card_id:
        card = await db.get(ProductCard, order.product_card_id)
        if card is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карточка товара для заказа не найдена")
        gtin_raw = card.gtin.strip() if card.gtin else None

    gtin14 = _normalize_gtin14_for_suz(gtin_raw)
    if not gtin14:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Для отправки в СУЗ нужен корректный GTIN.",
        )

    oms = await _resolve_oms_for_suz(db)
    if not oms.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Не задан OMS ID: укажите SUZ_OMS_ID в .env или добавьте устройство.",
        )

    settings = get_settings()
    prod_id = str(uuid4())
    body = build_suz_create_order_body(
        settings,
        product_group=settings.suz_product_group or "perfum",
        gtin14=gtin14,
        quantity=int(order.quantity),
        production_order_id=prod_id,
    )

    try:
        remote_oid, payload = await submit_suz_emission_order(oms_id=oms.strip(), json_body=body)
    except SuzIntegrationError as exc:
        hint = _SUZ_TRANSPORT_DIAG_HINT if exc.suggest_transport_diagnostics else ""
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"{exc}{hint}",
        ) from exc

    order.gtin = gtin14
    order.suz_order_id = remote_oid
    order.status = EmissionOrderStatus.PENDING
    await db.commit()
    await db.refresh(order)
    return order, remote_oid, payload
