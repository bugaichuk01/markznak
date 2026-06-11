import io
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.barcode.ecc200datamatrix import ECC200DataMatrix
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from models import GtinExtraFields

router = APIRouter(prefix="/labels", tags=["labels"])

_fonts_registered = False

def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    try:
        pdfmetrics.registerFont(
            TTFont('DejaVu', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        )
        pdfmetrics.registerFont(
            TTFont('DejaVuBold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
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


@router.post("/pdf")
async def generate_label_pdf(data: LabelRequest):
    _register_fonts()

    buf = io.BytesIO()
    w = data.width_mm * mm
    h = data.height_mm * mm

    c = canvas.Canvas(buf, pagesize=(w, h))

    font_normal = 'DejaVu' if _fonts_registered else 'Helvetica'
    font_bold = 'DejaVuBold' if _fonts_registered else 'Helvetica-Bold'

    # Левая часть — текст
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

    # DataMatrix занимает правую часть этикетки с отступами
    dm_size = min(h * 0.90, w * 0.48)  # не больше 90% высоты и 48% ширины
    dm_x = w - dm_size - 1 * mm        # прижать к правому краю с отступом 1мм
    dm_y = (h - dm_size) / 2           # по центру по высоте

    try:
        dm = ECC200DataMatrix(value=data.code, barWidth=1.0)
        dm.validate()
        dm.encode()

        rows = getattr(dm, 'row_modules', 44)
        cols = getattr(dm, 'col_modules', 44)

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
        }
    )


@router.post("/pdf/batch")
async def generate_batch_labels_pdf(
    data: BatchLabelRequest,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Генерировать PDF с несколькими этикетками (каждая — отдельная страница)."""
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

    def extract_gtin(code: str) -> str | None:
        m = re.match(r"^01(\d{14})", code)
        return m.group(1) if m else None

    gtins = list({extract_gtin(c) for c in data.codes if extract_gtin(c)})
    if gtins:
        result = await db.execute(
            select(GtinExtraFields).where(GtinExtraFields.gtin.in_(gtins))
        )
        for ef in result.scalars().all():
            extra_fields_cache[ef.gtin] = ef

    def draw_label(code: str, gtin: str | None) -> None:
        ef = extra_fields_cache.get(gtin) if gtin else None
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

    total_pages = len(data.codes) * data.copies
    page_num = 0
    for code in data.codes:
        gtin = extract_gtin(code)
        for _ in range(data.copies):
            draw_label(code, gtin)
            page_num += 1
            if page_num < total_pages:
                c.showPage()
                c.setPageSize((w, h))

    c.save()
    buf.seek(0)

    filename = f"labels_{len(data.codes)}pcs.pdf"
    return Response(
        content=buf.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )
