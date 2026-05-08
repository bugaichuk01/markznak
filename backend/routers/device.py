"""Эндпоинты настроек устройств ЧЗ (Device)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from schemas import DeviceCreate, DeviceFormDefaultsResponse, DeviceResponse
from services import device_service
from settings import get_settings

router = APIRouter(tags=["devices"])


@router.get("/devices/form-defaults", response_model=DeviceFormDefaultsResponse)
async def device_form_defaults() -> DeviceFormDefaultsResponse:
    s = get_settings()
    oms = (s.suz_oms_id or "").strip() or None
    conn = (s.suz_connection_id or "").strip() or None
    return DeviceFormDefaultsResponse(oms_id=oms, connection_id=conn)


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    session: AsyncSession = Depends(get_db_session),
) -> list[DeviceResponse]:
    return await device_service.list_devices(session)


@router.post(
    "/devices",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_device(
    data: DeviceCreate,
    session: AsyncSession = Depends(get_db_session),
) -> DeviceResponse:
    return await device_service.create_device(session, data)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    ok = await device_service.delete_device(session, device_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Устройство не найдено")
