import io
import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import eanbc
from reportlab.graphics.barcode.ecc200datamatrix import ECC200DataMatrix
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from dependencies import get_current_org, get_current_user
from models import (
    GtinExtraFields,
    LabelTemplate,
    OperationLogStatus,
    OperationLogType,
    Organization,
    User,
)
from schemas import LabelTemplateCreate, LabelTemplateResponse
from services.journal_service import log_operation

router = APIRouter(prefix="/labels", tags=["labels"])
logger = logging.getLogger(__name__)
_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    try:
        pdfmetrics.registerFont(
            TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        )
        pdfmetrics.registerFont(
            TTFont("DejaVuBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        )
        _fonts_registered = True
    except Exception as e:
        print(f"Шрифт не найден: {e}")


class LabelRequest(BaseModel):
    code: str
    name: str = ""
    article: str = ""
    gtin: str = ""
    size: str = ""
    width_mm: int = 58
    height_mm: int = 40


class BatchLabelRequest(BaseModel):
    codes: list[str]
    width_mm: int = 58
    height_mm: int = 40
    copies: int = 1
    template_id: str | None = None


class PrintFromTemplateRequest(BaseModel):
    template_id: str
    codes: list[str]
    copies: int = 1


def _extract_gtin(code: str) -> str | None:
    m = re.match(r"^01(\d{14})", code)
    return m.group(1) if m else None


def _substitute_text(
    template: str,
    *,
    name: str = "",
    article: str = "",
    gtin: str = "",
    size: str = "",
    brand: str = "",
    color: str = "",
    price: str = "",
) -> str:
    return (
        template.replace("{name}", name)
        .replace("{article}", article)
        .replace("{gtin}", gtin)
        .replace("{size}", size)
        .replace("{brand}", brand)
        .replace("{color}", color)
        .replace("{price}", price)
    )


def _gtin_to_ean13(gtin: str | None) -> str | None:
    if not gtin:
        return None
    digits = re.sub(r"\D", "", gtin)
    if len(digits) >= 13:
        return digits[:13]
    return None


def _draw_ean13(
    c: canvas.Canvas,
    gtin: str | None,
    x_mm: float,
    y_mm: float,
    width_mm: float,
    height_mm: float,
    page_h: float,
) -> None:
    barcode_value = _gtin_to_ean13(gtin)
    if not barcode_value:
        return

    bar_height = height_mm * mm
    bar_width = width_mm * mm
    text_gap = 5 * mm
    draw_y = page_h - y_mm * mm - bar_height - text_gap

    try:
        barcode = eanbc.Ean13BarcodeWidget(barcode_value)
        barcode.barHeight = bar_height
        barcode.barWidth = max(bar_width / 95.0, 0.2 * mm)

        drawing = Drawing(bar_width, bar_height + text_gap)
        drawing.add(barcode)
        renderPDF.draw(drawing, c, x_mm * mm, draw_y)
    except Exception as e:
        logger.warning("Ошибка генерации EAN-13: %s", e)


def _draw_datamatrix(c: canvas.Canvas, code: str, x_mm: float, y_mm: float, size_mm: float, page_h: float) -> None:
    dm_size = size_mm * mm
    dm_x = x_mm * mm
    dm_y = page_h - y_mm * mm - dm_size
    try:
        dm_probe = ECC200DataMatrix(value=code, barWidth=1.0)
        dm_probe.validate()
        dm_probe.encode()
        cols = dm_probe.col_modules
        rows = dm_probe.row_modules
        bar_size = dm_size / max(cols, rows)
        dm = ECC200DataMatrix(value=code, barWidth=bar_size)
        dm.validate()
        dm.encode()
        dm.canv = c
        dm.x = 0
        dm.y = 0
        c.saveState()
        c.translate(dm_x, dm_y)
        dm.draw()
        c.restoreState()
    except Exception:
        c.setFont("Helvetica", 3)
        c.drawString(dm_x, dm_y, code[:20])


def _draw_label_default(
    c: canvas.Canvas,
    code: str,
    gtin: str | None,
    ef: GtinExtraFields | None,
    w: float,
    h: float,
    font_normal: str,
    font_bold: str,
) -> None:
    product_name = ef.name if ef and ef.name else ""
    article = ef.article if ef and ef.article else ""
    size = ef.size if ef and ef.size else ""
    text_x = 2 * mm
    y = h - 4 * mm
    if product_name:
        c.setFont(font_bold, 5.5)
        c.drawString(text_x, y, product_name[:25])
        y -= 3.5 * mm
    c.setFont(font_normal, 4.5)
    if article:
        c.drawString(text_x, y, f"Арт: {article}")
        y -= 3 * mm
    if gtin:
        c.drawString(text_x, y, f"GTIN: {gtin}")
        y -= 3 * mm
    if size:
        c.drawString(text_x, y, f"Размер: {size}")
    dm_size = min(h * 0.90, w * 0.48)
    dm_x = w - dm_size - 1 * mm
    dm_y = (h - dm_size) / 2
    try:
        dm_probe = ECC200DataMatrix(value=code, barWidth=1.0)
        dm_probe.validate()
        dm_probe.encode()
        cols = dm_probe.col_modules
        rows = dm_probe.row_modules
        bar_size = dm_size / max(cols, rows)
        dm = ECC200DataMatrix(value=code, barWidth=bar_size)
        dm.validate()
        dm.encode()
        dm.canv = c
        dm.x = 0
        dm.y = 0
        c.saveState()
        c.translate(dm_x, dm_y)
        dm.draw()
        c.restoreState()
    except Exception:
        c.setFont(font_normal, 3)
        c.drawString(dm_x, dm_y, code[:20])


def _draw_label_from_template(
    c: canvas.Canvas,
    code: str,
    gtin: str | None,
    ef: GtinExtraFields | None,
    layout_data: dict,
    page_h: float,
    font_normal: str,
    font_bold: str,
) -> None:
    fields = {
        "name": ef.name if ef and ef.name else "",
        "article": ef.article if ef and ef.article else "",
        "gtin": gtin or "",
        "size": ef.size if ef and ef.size else "",
        "brand": ef.brand if ef and ef.brand else "",
        "color": ef.color if ef and ef.color else "",
        "price": "",
    }
    elements = layout_data.get("elements") or []
    for el in elements:
        el_type = el.get("type")
        if el_type == "datamatrix":
            _draw_datamatrix(
                c,
                code,
                float(el.get("x", 0)),
                float(el.get("y", 0)),
                float(el.get("size", 30)),
                page_h,
            )
        elif el_type == "barcode_ean13":
            _draw_ean13(
                c,
                gtin,
                float(el.get("x", 0)),
                float(el.get("y", 0)),
                float(el.get("width", 38)),
                float(el.get("height", 15)),
                page_h,
            )
        elif el_type == "text":
            text = _substitute_text(el.get("text", ""), **fields)
            if not text.strip():
                continue
            font_size = float(el.get("font_size", 6))
            is_bold = bool(el.get("bold"))
            font_name = font_bold if is_bold else font_normal
            c.setFont(font_name, font_size)
            x = float(el.get("x", 0)) * mm
            y = page_h - float(el.get("y", 0)) * mm - font_size * 0.35 * mm
            max_width = el.get("max_width")
            if max_width:
                max_w = float(max_width) * mm
                while stringWidth(text, font_name, font_size) > max_w and len(text) > 1:
                    text = text[:-1]
            c.drawString(x, y, text)
        elif el_type == "line":
            x1 = float(el.get("x1", el.get("x", 0))) * mm
            y1 = page_h - float(el.get("y1", el.get("y", 0))) * mm
            x2 = float(el.get("x2", 0)) * mm
            y2 = page_h - float(el.get("y2", el.get("y", 0))) * mm
            c.setLineWidth(0.5)
            c.line(x1, y1, x2, y2)


async def _generate_batch_labels_pdf(
    data: BatchLabelRequest,
    db: AsyncSession,
    org: Organization | None,
    layout_data: dict | None = None,
) -> Response:
    _register_fonts()
    if not data.codes:
        raise HTTPException(status_code=400, detail="Список кодов пуст")
    if len(data.codes) > 500:
        raise HTTPException(status_code=400, detail="Максимум 500 этикеток за один запрос")
    if data.copies < 1 or data.copies > 10:
        raise HTTPException(status_code=400, detail="Количество копий: от 1 до 10")

    w = data.width_mm * mm
    h = data.height_mm * mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    font_normal = "DejaVu" if _fonts_registered else "Helvetica"
    font_bold = "DejaVuBold" if _fonts_registered else "Helvetica-Bold"

    extra_fields_cache: dict[str, GtinExtraFields] = {}
    gtins = list({_extract_gtin(code) for code in data.codes if _extract_gtin(code)})
    if gtins:
        q = select(GtinExtraFields).where(GtinExtraFields.gtin.in_(gtins))
        if org:
            q = q.where(GtinExtraFields.org_id == org.id)
        result = await db.execute(q)
        for ef in result.scalars().all():
            extra_fields_cache[ef.gtin] = ef

    def draw_label(code: str, gtin: str | None) -> None:
        ef = extra_fields_cache.get(gtin) if gtin else None
        if layout_data and layout_data.get("elements"):
            _draw_label_from_template(c, code, gtin, ef, layout_data, h, font_normal, font_bold)
        else:
            _draw_label_default(c, code, gtin, ef, w, h, font_normal, font_bold)

    total_pages = len(data.codes) * data.copies
    page_num = 0
    for code in data.codes:
        gtin = _extract_gtin(code)
        for _ in range(data.copies):
            draw_label(code, gtin)
            page_num += 1
            if page_num < total_pages:
                c.showPage()
                c.setPageSize((w, h))

    c.save()
    buf.seek(0)
    await log_operation(
        db,
        operation_type=OperationLogType.LABEL_PRINTED,
        status=OperationLogStatus.SUCCESS,
        description=f"Напечатано {len(data.codes)} этикеток",
        codes_count=len(data.codes),
        org_id=org.id if org else None,
    )
    filename = f"labels_{len(data.codes)}pcs.pdf"
    return Response(
        content=buf.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


@router.get("/templates", response_model=list[LabelTemplateResponse])
async def list_templates(
    _: User = Depends(get_current_user),
    org: Organization | None = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_session),
) -> list[LabelTemplateResponse]:
    """Список шаблонов этикеток."""
    q = (
        select(LabelTemplate)
        .where(
            or_(
                LabelTemplate.org_id == (org.id if org else None),
                LabelTemplate.org_id.is_(None),
            )
        )
        .order_by(LabelTemplate.is_default.desc(), LabelTemplate.created_at)
    )
    result = await db.scalars(q)
    return list(result.all())


@router.post("/templates", response_model=LabelTemplateResponse, status_code=201)
async def create_template(
    data: LabelTemplateCreate,
    _: User = Depends(get_current_user),
    org: Organization | None = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_session),
) -> LabelTemplateResponse:
    """Создать шаблон этикетки."""
    template = LabelTemplate(
        name=data.name,
        width_mm=data.width_mm,
        height_mm=data.height_mm,
        layout_data=data.layout_data,
        is_default=data.is_default,
        org_id=org.id if org else None,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.put("/templates/{template_id}", response_model=LabelTemplateResponse)
async def update_template(
    template_id: UUID,
    data: LabelTemplateCreate,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> LabelTemplateResponse:
    """Обновить шаблон."""
    template = await db.get(LabelTemplate, template_id)
    if not template:
        raise HTTPException(404, "Шаблон не найден")
    template.name = data.name
    template.width_mm = data.width_mm
    template.height_mm = data.height_mm
    template.layout_data = data.layout_data
    template.is_default = data.is_default
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Удалить шаблон."""
    template = await db.get(LabelTemplate, template_id)
    if not template:
        raise HTTPException(404, "Шаблон не найден")
    await db.delete(template)
    await db.commit()


@router.post("/pdf/from-template")
async def print_from_template(
    data: PrintFromTemplateRequest,
    _: User = Depends(get_current_user),
    org: Organization | None = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Печать по шаблону."""
    if not data.template_id or not data.codes:
        raise HTTPException(400, "Укажите template_id и codes")

    template = await db.get(LabelTemplate, UUID(data.template_id))
    if not template:
        raise HTTPException(404, "Шаблон не найден")

    return await _generate_batch_labels_pdf(
        data=BatchLabelRequest(
            codes=data.codes,
            width_mm=template.width_mm,
            height_mm=template.height_mm,
            copies=data.copies,
        ),
        db=db,
        org=org,
        layout_data=template.layout_data,
    )


@router.post("/pdf")
async def generate_label_pdf(
    data: LabelRequest,
    _: User = Depends(get_current_user),
):
    _register_fonts()
    buf = io.BytesIO()
    w = data.width_mm * mm
    h = data.height_mm * mm
    c = canvas.Canvas(buf, pagesize=(w, h))
    font_normal = "DejaVu" if _fonts_registered else "Helvetica"
    font_bold = "DejaVuBold" if _fonts_registered else "Helvetica-Bold"
    text_x = 2 * mm
    y = h - 4 * mm
    if data.name:
        c.setFont(font_bold, 5.5)
        c.drawString(text_x, y, data.name[:25])
        y -= 3.5 * mm
    c.setFont(font_normal, 4.5)
    if data.article:
        c.drawString(text_x, y, f"Арт: {data.article}")
        y -= 3 * mm
    if data.gtin:
        c.drawString(text_x, y, f"GTIN: {data.gtin}")
        y -= 3 * mm
    if data.size:
        c.drawString(text_x, y, f"Размер: {data.size}")
    dm_size = min(h * 0.90, w * 0.48)
    dm_x = w - dm_size - 1 * mm
    dm_y = (h - dm_size) / 2
    try:
        dm = ECC200DataMatrix(value=data.code, barWidth=1.0)
        dm.validate()
        dm.encode()
        rows = getattr(dm, "row_modules", 44)
        cols = getattr(dm, "col_modules", 44)
        bar_size = min(dm_size / cols, dm_size / rows)
        dm2 = ECC200DataMatrix(value=data.code, barWidth=bar_size)
        dm2.validate()
        dm2.encode()
        dm2.canv = c
        dm2.x = 0
        dm2.y = 0
        c.saveState()
        c.translate(dm_x, dm_y)
        dm2.draw()
        c.restoreState()
    except Exception as e:
        print(f"Ошибка DataMatrix: {e}")
    c.save()
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline; filename=label.pdf",
        },
    )


@router.post("/pdf/batch")
async def generate_batch_labels_pdf(
    data: BatchLabelRequest,
    _: User = Depends(get_current_user),
    org: Organization | None = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    layout_data: dict | None = None
    if data.template_id:
        template = await db.get(LabelTemplate, UUID(data.template_id))
        if template:
            layout_data = template.layout_data
            data = data.model_copy(
                update={
                    "width_mm": template.width_mm,
                    "height_mm": template.height_mm,
                }
            )
    return await _generate_batch_labels_pdf(data, db, org, layout_data=layout_data)
