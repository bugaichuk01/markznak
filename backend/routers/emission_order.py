"""Эндпоинты для заказов на эмиссию кодов (СУЗ)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from models import EmissionOrder
from schemas import (
    CisStatusItem,
    CisStatusRequest,
    CisStatusResponse,
    CloseOrderRequest,
    CloseOrderResponse,
    EmissionOrderCreate,
    EmissionOrderGtinPatch,
    EmissionOrderResponse,
    EmissionOrderStatusUpdateRequest,
    FetchCodesResponse,
    MarkingCodePrintOptionsResponse,
    MarkingCodesListResponse,
    MergeOrdersRequest,
    SuzConnectivityDiagnosticsResponse,
    SuzCreateOrderProxyRequest,
    SuzOrderPayloadPreview,
    SuzSendOrderPayload,
    SuzSendOrderRequest,
    SuzSendOrderResponse,
    SuzSyncResponse,
)
from services import emission_order_service
from services.suz_diagnostic_service import diagnose_suz_oms_endpoint
from services.suz_integration_service import check_cis_statuses_batch

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


@router.get("/codes", response_model=MarkingCodesListResponse)
async def list_marking_codes(
    gtin: str | None = None,
    order_id: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
) -> MarkingCodesListResponse:
    data = await emission_order_service.list_all_marking_codes(
        db,
        gtin=gtin,
        order_id=order_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return MarkingCodesListResponse(**data)


@router.post("/codes/check-status", response_model=CisStatusResponse)
async def check_codes_status(
    request: CisStatusRequest,
    db: AsyncSession = Depends(get_db_session),
) -> CisStatusResponse:
    """Проверить статус кодов маркировки через True API ЧЗ."""
    if len(request.cises) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Максимум 50 кодов за один запрос",
        )

    results = await check_cis_statuses_batch(request.cises, db=db)
    items = [
        CisStatusItem(
            cis=r["cis"],
            status=r.get("status"),
            owner_inn=r.get("owner_inn"),
            owner_name=r.get("owner_name"),
            gtin=r.get("gtin"),
            produced_date=r.get("produced_date"),
            error=r.get("error"),
        )
        for r in results
    ]
    return CisStatusResponse(
        results=items,
        total=len(request.cises),
        checked=len([r for r in results if "error" not in r]),
    )


@router.get("/diagnostics/connectivity", response_model=SuzConnectivityDiagnosticsResponse)
async def suz_connectivity_diagnostics() -> SuzConnectivityDiagnosticsResponse:
    data = await diagnose_suz_oms_endpoint()
    return SuzConnectivityDiagnosticsResponse.model_validate(data)


@router.post("/create", response_model=SuzSendOrderResponse)
async def create_suz_order_proxy(
    data: SuzCreateOrderProxyRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SuzSendOrderResponse:
    """
    Прокси в СУЗ: подпись X-Signature формируется только в браузере (cadesplugin).
    Backend не вызывает КриптоПро и передаёт body_string в API без повторной сериализации.
    """
    emission_order, suz_remote_id, raw_payload = await emission_order_service.create_suz_order_via_proxy(
        body_string=data.body_string,
        signature=data.signature,
        db=db,
        local_order_id=data.local_order_id,
    )
    return SuzSendOrderResponse(
        emission_order=(
            EmissionOrderResponse.model_validate(emission_order) if emission_order is not None else None
        ),
        suz=SuzSendOrderPayload(remote_order_id=suz_remote_id, payload=raw_payload),
    )


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


@router.get("/{order_id}/suz-order-payload", response_model=SuzOrderPayloadPreview)
async def get_suz_order_send_payload(
    order_id: UUID,
    release_method_type: str | None = None,
    producer: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> SuzOrderPayloadPreview:
    data = await emission_order_service.prepare_suz_order_send_payload(
        order_id,
        db,
        release_method_type=release_method_type,
        producer=producer,
    )
    return SuzOrderPayloadPreview.model_validate(data)


@router.post("/{order_id}/send", response_model=SuzSendOrderResponse)
async def send_emission_order_to_suz(
    order_id: UUID,
    data: SuzSendOrderRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SuzSendOrderResponse:
    emission_order, suz_remote_id, raw_payload = await emission_order_service.send_order_to_suz(
        order_id,
        db,
        body_string=data.body_string,
        signature=data.signature,
    )
    return SuzSendOrderResponse(
        emission_order=EmissionOrderResponse.model_validate(emission_order),
        suz=SuzSendOrderPayload(remote_order_id=suz_remote_id, payload=raw_payload),
    )


@router.post("/{order_id}/fetch-codes", response_model=FetchCodesResponse)
async def fetch_codes_from_suz(
    order_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> FetchCodesResponse:
    """Скачать КМ из СУЗ и сохранить в БД."""
    order, codes = await emission_order_service.download_order_codes(order_id, db)
    return FetchCodesResponse(
        order_id=order_id,
        codes_count=len(codes),
        status=order.status.value,
    )


@router.post("/{order_id}/close", response_model=CloseOrderResponse)
async def close_emission_order(
    order_id: UUID,
    data: CloseOrderRequest,
    db: AsyncSession = Depends(get_db_session),
) -> CloseOrderResponse:
    """Закрыть заказ в СУЗ (подпись делается на фронте)."""
    order = await emission_order_service.close_order(
        order_id, db, signature=data.signature
    )
    return CloseOrderResponse(
        success=True,
        order_id=str(order_id),
        status=order.status.value,
    )


@router.get("/{order_id}/codes.csv")
async def download_codes_csv(
    order_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Скачать КМ в виде CSV файла."""
    order = await db.get(EmissionOrder, order_id)
    if order is None or not order.suz_marking_codes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Коды не найдены")

    content = "\n".join(order.suz_marking_codes)
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=codes_{order_id}.csv"
        },
    )
