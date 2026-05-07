from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import device, emission_order, excel, ozon, product_card, upd
from settings import get_settings

app = FastAPI(title="MarkZnak Clone API", version="0.1.0", docs_url="/docs")

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(device.router)
api_v1.include_router(ozon.router)
api_v1.include_router(excel.router)
api_v1.include_router(upd.router)
api_v1.include_router(product_card.router)
api_v1.include_router(emission_order.router)
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
