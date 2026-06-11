"""Дополнительные поля к GTIN (этикетки, УПД)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from models import GtinExtraFields
from schemas import (
    GtinExtraFieldsCreate,
    GtinExtraFieldsListResponse,
    GtinExtraFieldsResponse,
    GtinExtraFieldsUpdate,
)

router = APIRouter(prefix="/extra-fields", tags=["extra-fields"])


@router.get("/", response_model=GtinExtraFieldsListResponse)
async def list_extra_fields(
    gtin: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> GtinExtraFieldsListResponse:
    q = select(GtinExtraFields)
    if gtin:
        q = q.where(GtinExtraFields.gtin == gtin)
    q = q.order_by(GtinExtraFields.created_at.desc())
    items = list((await db.scalars(q)).all())
    return GtinExtraFieldsListResponse(items=items, total=len(items))


@router.post("/", response_model=GtinExtraFieldsResponse)
async def create_or_update_extra_fields(
    data: GtinExtraFieldsCreate,
    db: AsyncSession = Depends(get_db_session),
) -> GtinExtraFields:
    existing = await db.scalar(
        select(GtinExtraFields).where(GtinExtraFields.gtin == data.gtin)
    )
    if existing:
        for key, value in data.model_dump(exclude={"gtin"}).items():
            if value is not None:
                setattr(existing, key, value)
        await db.commit()
        await db.refresh(existing)
        return existing

    record = GtinExtraFields(**data.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.patch("/{gtin}", response_model=GtinExtraFieldsResponse)
async def update_extra_fields(
    gtin: str,
    data: GtinExtraFieldsUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> GtinExtraFields:
    record = await db.scalar(
        select(GtinExtraFields).where(GtinExtraFields.gtin == gtin)
    )
    if not record:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Доп. поля для GTIN не найдены",
        )
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(record, key, value)
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{gtin}")
async def delete_extra_fields(
    gtin: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    record = await db.scalar(
        select(GtinExtraFields).where(GtinExtraFields.gtin == gtin)
    )
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Не найдено")
    await db.delete(record)
    await db.commit()
    return {"success": True}
