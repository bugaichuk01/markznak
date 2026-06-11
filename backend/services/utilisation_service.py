"""Сервис ввода КМ в оборот через отчёт о нанесении."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import UtilisationReport, UtilisationStatus
from schemas import UtilisationReportCreate
from services.suz_integration_service import (
    _normalize_suz_client_token,
    _suz_dispatch_httpx,
)
from services.token_service import get_active_token
from settings import get_settings

logger = logging.getLogger(__name__)


def normalize_marking_code(code: str) -> str:
    """
    Восстанавливает GS1 разделители \\x1d в коде маркировки.

    Полный формат: 01{14}21{13}\\x1d91{4}\\x1d92{44}=
    Если \\x1d уже есть — возвращаем как есть.
    """
    gs = "\x1d"

    if gs in code:
        return code

    pattern = re.compile(
        r"^(01\d{14})"
        r"(21.+?)"
        r"(91[A-F0-9]{4})"
        r"(92.+)$",
        re.IGNORECASE,
    )

    m = pattern.match(code)
    if m:
        part1 = m.group(1) + m.group(2)
        part2 = m.group(3)
        part3 = m.group(4)
        return f"{part1}{gs}{part2}{gs}{part3}"

    idx_91 = code.find("91FFD0")
    if idx_91 == -1:
        for i in range(30, len(code) - 6):
            if code[i : i + 2] == "91" and code[i + 6 : i + 8] == "92":
                idx_91 = i
                break

    if idx_91 > 0:
        idx_92 = code.find("92", idx_91 + 4)
        if idx_92 > 0:
            return f"{code[:idx_91]}{gs}{code[idx_91:idx_92]}{gs}{code[idx_92:]}"

    return code


def normalize_codes_for_utilisation(codes: list[str]) -> list[str]:
    """Нормализовать список кодов перед отправкой в ЧЗ."""
    return [normalize_marking_code(code) for code in codes]


async def create_utilisation_draft(
    data: UtilisationReportCreate,
    db: AsyncSession,
) -> UtilisationReport:
    """Создать черновик отчёта о нанесении."""
    report = UtilisationReport(
        product_group=data.product_group,
        marking_codes=data.marking_codes,
        status=UtilisationStatus.DRAFT,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


def build_utilisation_body(
    marking_codes: list[str],
    product_group: str = "perfumery",
) -> dict:
    """Сформировать тело запроса для отчёта о нанесении."""
    normalized_codes = normalize_codes_for_utilisation(marking_codes)
    return {
        "productGroup": product_group,
        "sntins": normalized_codes,
    }


def serialize_utilisation_body(body_dict: dict) -> str:
    """Каноническая сериализация — та же строка подписывается в браузере."""
    return json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))


async def get_utilisation_body_for_signing(
    report_id: UUID,
    db: AsyncSession,
) -> tuple[UtilisationReport, str]:
    """Получить тело запроса для подписи на фронте."""
    report = await db.get(UtilisationReport, report_id)
    if report is None:
        raise LookupError("Отчёт не найден")
    body_dict = build_utilisation_body(report.marking_codes, report.product_group)
    body_str = serialize_utilisation_body(body_dict)
    return report, body_str


async def send_utilisation_report(
    report_id: UUID,
    signature: str,
    db: AsyncSession,
) -> UtilisationReport:
    """Отправить отчёт о нанесении в СУЗ с подписью от фронта."""
    report = await db.get(UtilisationReport, report_id)
    if report is None:
        raise LookupError("Отчёт не найден")
    if report.status not in (UtilisationStatus.DRAFT, UtilisationStatus.ERROR):
        raise ValueError(f"Нельзя отправить отчёт со статусом {report.status}")

    settings = get_settings()
    token_raw = await get_active_token(db)
    token = _normalize_suz_client_token(token_raw or "")
    oms_id = settings.suz_oms_id or ""
    base_url = (settings.suz_api_base_url or "").rstrip("/")

    if not token:
        raise ValueError("Не задан clientToken СУЗ")
    if not oms_id:
        raise ValueError("Не задан OMS ID")

    body_dict = build_utilisation_body(report.marking_codes, report.product_group)
    body_str = serialize_utilisation_body(body_dict)

    url = f"{base_url}/api/v3/utilisation?omsId={oms_id}"
    headers = {
        "clientToken": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Signature": signature.replace("\r", "").replace("\n", "").strip(),
    }

    report.signature_value = headers["X-Signature"]
    report.status = UtilisationStatus.PENDING

    response, err = await _suz_dispatch_httpx(
        method="POST",
        url=url,
        headers=headers,
        params=None,
        content=body_str.encode("utf-8"),
    )

    if response is None:
        report.status = UtilisationStatus.ERROR
        report.error_message = str(err)
        await db.commit()
        raise RuntimeError(f"Ошибка отправки отчёта: {err}")

    if response.status_code in (200, 201, 202):
        try:
            resp_data = response.json()
            report.report_id = str(
                resp_data.get("reportId")
                or resp_data.get("id")
                or resp_data.get("omsId")
                or ""
            ) or None
        except Exception:
            report.report_id = None
        report.status = UtilisationStatus.ACCEPTED
        report.sent_at = datetime.now(timezone.utc)
        report.error_message = None
    else:
        report.status = UtilisationStatus.ERROR
        report.error_message = response.text[:500]
        await db.commit()
        raise RuntimeError(
            f"СУЗ отклонил отчёт ({response.status_code}): {response.text[:200]}"
        )

    await db.commit()
    await db.refresh(report)
    return report


async def list_utilisation_reports(db: AsyncSession) -> list[UtilisationReport]:
    """Список отчётов о нанесении."""
    result = await db.scalars(
        select(UtilisationReport).order_by(UtilisationReport.created_at.desc())
    )
    return list(result.all())
