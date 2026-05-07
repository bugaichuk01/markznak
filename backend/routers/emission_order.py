"""Эндпоинты для заказов на эмиссию кодов (СУЗ)."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from schemas import (
    EmissionOrderCreate,
    EmissionOrderResponse,
    EmissionOrderStatusUpdateRequest,
    MergeOrdersRequest,
)
from services import emission_order_service

router = APIRouter(prefix="/emission-orders", tags=["SUZ"])


@router.post("/", response_model=EmissionOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_emission_order(
    data: EmissionOrderCreate,
    db: AsyncSession = Depends(get_db_session),
) -> EmissionOrderResponse:
    return await emission_order_service.create_order(data, db)


@router.get("/", response_model=list[EmissionOrderResponse])
async def list_emission_orders(
    db: AsyncSession = Depends(get_db_session),
) -> list[EmissionOrderResponse]:
    return await emission_order_service.get_orders(db)


@router.patch("/{order_id}/status", response_model=EmissionOrderResponse)
async def patch_emission_order_status(
    order_id: UUID,
    data: EmissionOrderStatusUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EmissionOrderResponse:
    return await emission_order_service.update_order_status(order_id, data.status.value, db)


@router.post("/merge", response_model=EmissionOrderResponse, status_code=status.HTTP_201_CREATED)
async def merge_emission_orders(
    data: MergeOrdersRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EmissionOrderResponse:
    return await emission_order_service.merge_orders(data.order_ids, db)
