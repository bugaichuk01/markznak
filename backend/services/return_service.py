"""Сервис возврата КМ в оборот."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import OperationLogStatus, OperationLogType, ReturnDocument, ReturnStatus
from services.journal_service import log_operation
from schemas import ReturnDocumentCreate
from services.suz_integration_service import _suz_dispatch_httpx
from services.token_service import get_true_api_token
from settings import get_settings

logger = logging.getLogger(__name__)


async def create_return_draft(
    data: ReturnDocumentCreate,
    db: AsyncSession,
    org_id: UUID | None = None,
) -> ReturnDocument:
    doc = ReturnDocument(
        return_type=data.return_type,
        product_group=data.product_group,
        marking_codes=data.marking_codes,
        status=ReturnStatus.DRAFT,
        org_id=org_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


def build_return_document(
    marking_codes: list[str],
    return_type: str = "RETURN",
) -> dict:
    return {
        "return_type": return_type,
        "return_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "cises": marking_codes,
    }


async def get_return_body_for_signing(
    doc_id: UUID,
    db: AsyncSession,
) -> tuple[ReturnDocument, str, str]:
    doc = await db.get(ReturnDocument, doc_id)
    if doc is None:
        raise LookupError("Документ не найден")
    body_dict = build_return_document(doc.marking_codes, doc.return_type)
    body_json = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    body_b64 = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
    return doc, body_json, body_b64


async def send_return_document(
    doc_id: UUID,
    signature: str,
    db: AsyncSession,
) -> ReturnDocument:
    doc = await db.get(ReturnDocument, doc_id)
    if doc is None:
        raise LookupError("Документ не найден")
    if doc.status not in (ReturnStatus.DRAFT, ReturnStatus.ERROR):
        raise ValueError(f"Нельзя отправить документ со статусом {doc.status}")

    settings = get_settings()
    token = await get_true_api_token(db)
    base_url = (settings.true_api_base_url or "").rstrip("/")

    if not token:
        raise ValueError("Не настроен JWT токен True API")

    body_dict = build_return_document(doc.marking_codes, doc.return_type)
    body_json = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    body_b64 = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")

    request_body = {
        "document_format": "MANUAL",
        "type": "LP_RETURN",
        "product_document": body_b64,
        "signature": signature,
    }

    url = f"{base_url}/api/v3/true-api/lk/documents/create"
    params = {"pg": doc.product_group}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body_str = json.dumps(request_body, ensure_ascii=False)

    logger.info(
        "Return request: url=%s, pg=%s, codes=%d",
        url,
        doc.product_group,
        len(doc.marking_codes),
    )

    doc.signature_value = signature.replace("\r", "").replace("\n", "").strip()
    doc.status = ReturnStatus.PENDING

    response, err = await _suz_dispatch_httpx(
        method="POST",
        url=url,
        headers=headers,
        params=params,
        content=body_str.encode("utf-8"),
    )

    if response is None:
        doc.status = ReturnStatus.ERROR
        doc.error_message = str(err)
        await db.commit()
        await log_operation(
            db,
            operation_type=OperationLogType.RETURN_SENT,
            status=OperationLogStatus.ERROR,
            description="Ошибка возврата в оборот",
            related_id=str(doc.id),
            related_type="return_document",
            codes_count=len(doc.marking_codes),
            error_message=str(err)[:500],
        )
        raise RuntimeError(f"Ошибка отправки: {err}")

    logger.info(
        "Return response: status=%d, body=%s",
        response.status_code,
        response.text[:300],
    )

    if response.status_code in (200, 201, 202):
        try:
            resp_data = response.json()
            doc.document_id = str(
                resp_data.get("id")
                or resp_data.get("documentId")
                or resp_data.get("document_id")
                or ""
            ) or None
        except Exception:
            doc.document_id = None
        doc.status = ReturnStatus.ACCEPTED
        doc.sent_at = datetime.now(timezone.utc)
        doc.error_message = None
    else:
        doc.status = ReturnStatus.ERROR
        doc.error_message = response.text[:500]
        await db.commit()
        await log_operation(
            db,
            operation_type=OperationLogType.RETURN_SENT,
            status=OperationLogStatus.ERROR,
            description="Ошибка возврата в оборот",
            related_id=str(doc.id),
            related_type="return_document",
            codes_count=len(doc.marking_codes),
            error_message=response.text[:500],
        )
        raise RuntimeError(
            f"True API отклонил документ ({response.status_code}): {response.text[:300]}"
        )

    await db.commit()
    await db.refresh(doc)
    await log_operation(
        db,
        operation_type=OperationLogType.RETURN_SENT,
        status=OperationLogStatus.SUCCESS,
        description=f"Возврат в оборот: {len(doc.marking_codes)} кодов",
        related_id=str(doc.id),
        related_type="return_document",
        codes_count=len(doc.marking_codes),
        details={"document_id": doc.document_id, "return_type": doc.return_type},
    )
    return doc


async def list_return_documents(
    db: AsyncSession,
    org_id: UUID | None = None,
) -> list[ReturnDocument]:
    q = select(ReturnDocument)
    if org_id:
        q = q.where(ReturnDocument.org_id == org_id)
    result = await db.scalars(q.order_by(ReturnDocument.created_at.desc()))
    return list(result.all())
