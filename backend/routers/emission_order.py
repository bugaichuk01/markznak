"""Эндпоинты для заказов на эмиссию кодов (СУЗ)."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from schemas import (
    EmissionOrderCreate,
    EmissionOrderGtinPatch,
    EmissionOrderResponse,
    EmissionOrderStatusUpdateRequest,
    MarkingCodePrintOptionsResponse,
    MergeOrdersRequest,
    SuzConnectivityDiagnosticsResponse,
    SuzSendOrderPayload,
    SuzSendOrderResponse,
    SuzSyncResponse,
)
from services import emission_order_service
from services.suz_diagnostic_service import diagnose_suz_oms_endpoint

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


@router.get("/marking-codes-for-print", response_model=MarkingCodePrintOptionsResponse)
async def list_marking_codes_for_print(
    db: AsyncSession = Depends(get_db_session),
) -> MarkingCodePrintOptionsResponse:
    codes = await emission_order_service.list_marking_codes_for_print(db)
    return MarkingCodePrintOptionsResponse(codes=codes)


@router.get("/diagnostics/connectivity", response_model=SuzConnectivityDiagnosticsResponse)
async def suz_connectivity_diagnostics() -> SuzConnectivityDiagnosticsResponse:
    data = await diagnose_suz_oms_endpoint()
    return SuzConnectivityDiagnosticsResponse.model_validate(data)


@router.post("/sync-from-suz", response_model=SuzSyncResponse)
async def sync_emission_orders_from_suz(
    db: AsyncSession = Depends(get_db_session),
) -> SuzSyncResponse:
    data = await emission_order_service.sync_orders_from_suz(db)
    return SuzSyncResponse(**data)


@router.post("/merge", response_model=EmissionOrderResponse, status_code=status.HTTP_201_CREATED)
async def merge_emission_orders(
    data: MergeOrdersRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EmissionOrderResponse:
    return await emission_order_service.merge_orders(data.order_ids, db)


@router.patch("/{order_id}/status", response_model=EmissionOrderResponse)
async def patch_emission_order_status(
    order_id: UUID,
    data: EmissionOrderStatusUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> EmissionOrderResponse:
    return await emission_order_service.update_order_status(order_id, data.status.value, db)


@router.patch("/{order_id}/gtin", response_model=EmissionOrderResponse)
async def patch_emission_order_gtin(
    order_id: UUID,
    data: EmissionOrderGtinPatch,
    db: AsyncSession = Depends(get_db_session),
) -> EmissionOrderResponse:
    return await emission_order_service.patch_order_gtin(order_id, data.gtin, db)


@router.post("/{order_id}/send", response_model=SuzSendOrderResponse)
async def send_emission_order_to_suz(
    order_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> SuzSendOrderResponse:
    emission_order, suz_remote_id, raw_payload = await emission_order_service.send_order_to_suz(order_id, db)
    return SuzSendOrderResponse(
        emission_order=EmissionOrderResponse.model_validate(emission_order),
        suz=SuzSendOrderPayload(remote_order_id=suz_remote_id, payload=raw_payload),
    )
