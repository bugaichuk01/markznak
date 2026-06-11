import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import (
    device,
    emission_order,
    excel,
    extra_fields,
    labels,
    ozon,
    product_card,
    token as token_router,
    upd,
    utilisation as utilisation_router,
    withdrawal as withdrawal_router,
)
from services.token_service import refresh_token_background
from settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(refresh_token_background())
    logger.info("Фоновый мониторинг токена СУЗ запущен")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Знак API", version="0.1.0", docs_url="/docs", lifespan=lifespan)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(device.router)
api_v1.include_router(ozon.router)
api_v1.include_router(excel.router)
api_v1.include_router(upd.router)
api_v1.include_router(product_card.router)
api_v1.include_router(emission_order.router)
api_v1.include_router(extra_fields.router)
api_v1.include_router(labels.router)
api_v1.include_router(token_router.router)
api_v1.include_router(utilisation_router.router)
api_v1.include_router(withdrawal_router.router)
app.include_router(api_v1)

_settings = get_settings()
_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
