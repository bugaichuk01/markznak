"""Создание черновика УПД в БД."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DocumentUPD
from schemas import DocumentStatus, UpdCreateRequest


async def create_upd_draft(session: AsyncSession, data: UpdCreateRequest) -> DocumentUPD:
    """
    Сохраняет УПД со статусом draft.
    Для commercial_edo XML пока не генерируем — только запись в БД.
    """
    doc = DocumentUPD(
        document_number=data.document_number.strip(),
        marking_codes=list(data.marking_codes),
        disable_owner_control=data.disable_owner_control,
        edo_type=data.edo_type.value,
        status=DocumentStatus.DRAFT.value,
        xml_draft_content=None,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def get_upd_document(session: AsyncSession, document_id: UUID) -> DocumentUPD:
    """Возвращает УПД-документ или возбуждает LookupError."""
    result = await session.execute(select(DocumentUPD).where(DocumentUPD.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise LookupError("UPD document not found")
    return document
