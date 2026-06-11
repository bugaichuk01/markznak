"""Эндпоинты УПД."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from database import get_db_session
from models import DocumentUPD
from schemas import DocumentUPDResponse, UpdCreateRequest, UpdSendRequest
from services import edo_integration_service, upd_service, xml_generator_service

router = APIRouter(tags=["upd"])


@router.get("/upd/list", response_model=list[DocumentUPDResponse])
async def list_upds(
    session: AsyncSession = Depends(get_db_session),
) -> list[DocumentUPD]:
    result = await session.execute(
        select(DocumentUPD).order_by(DocumentUPD.created_at.desc()).limit(50)
    )
    return list(result.scalars().all())


@router.post(
    "/upd/create",
    response_model=DocumentUPDResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_upd(
    data: UpdCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentUPDResponse:
    doc = await upd_service.create_upd_draft(session, data)
    return doc


@router.get("/upd/{id}/download-xml")
async def download_upd_xml(
    id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        xml_content = await xml_generator_service.generate_upd_xml(id, session)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    headers = {"Content-Disposition": 'attachment; filename="upd_draft.xml"'}
    return Response(content=xml_content, media_type="application/xml", headers=headers)


@router.post(
    "/upd/{id}/send",
    response_model=DocumentUPDResponse,
)
async def send_upd_to_edo(
    id: UUID,
    payload: UpdSendRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentUPDResponse:
    try:
        doc = await edo_integration_service.sign_and_send_document(id, payload, session)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return doc
