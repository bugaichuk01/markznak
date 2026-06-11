"""Эндпоинты вывода КМ из оборота."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from models import WithdrawalReport
from schemas import (
    WithdrawalBodyPreview,
    WithdrawalReportCreate,
    WithdrawalReportResponse,
    WithdrawalSendRequest,
)
from services import withdrawal_service

router = APIRouter(prefix="/withdrawal", tags=["withdrawal"])


@router.post(
    "/",
    response_model=WithdrawalReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_report(
    data: WithdrawalReportCreate,
    db: AsyncSession = Depends(get_db_session),
) -> WithdrawalReportResponse:
    if not data.marking_codes:
        raise HTTPException(status_code=400, detail="Список кодов пуст")
    if len(data.marking_codes) > 5000:
        raise HTTPException(status_code=400, detail="Максимум 5000 кодов")
    return await withdrawal_service.create_withdrawal_draft(data, db)


@router.get("/", response_model=list[WithdrawalReportResponse])
async def list_reports(
    db: AsyncSession = Depends(get_db_session),
) -> list[WithdrawalReportResponse]:
    return await withdrawal_service.list_withdrawal_reports(db)


@router.get("/{report_id}/body", response_model=WithdrawalBodyPreview)
async def get_body_for_signing(
    report_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> WithdrawalBodyPreview:
    try:
        _report, doc_json, doc_b64 = await withdrawal_service.get_withdrawal_body_for_signing(
            report_id, db
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return WithdrawalBodyPreview(body=doc_json, body_b64=doc_b64)


@router.post("/{report_id}/send", response_model=WithdrawalReportResponse)
async def send_report(
    report_id: UUID,
    payload: WithdrawalSendRequest,
    db: AsyncSession = Depends(get_db_session),
) -> WithdrawalReportResponse:
    try:
        return await withdrawal_service.send_withdrawal_report(
            report_id, payload.signature, db
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.delete("/{report_id}", status_code=204)
async def delete_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    report = await db.get(WithdrawalReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    await db.delete(report)
    await db.commit()
