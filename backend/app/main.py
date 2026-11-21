from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logging
logger = logging.getLogger(__name__)
from app.core.config import settings
from app.core.database import init_db
from app.core.ops_metrics import register_ops_metrics
from app.api.routes import (
    options,
    auth,
    users,
    brokers,
    strategies,
    trades,
    websocket,
    admin,
    signals,
    risk,
    market,
    backtest,
    formula,
    terminal,
    copy_trading,
)
from app.api.routes.dhan_auth_route import router as dhan_auth_router
from app.api.routes.settings import router as settings_router


import app.models  # noqa


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        from app.broker.dhan_auth import get_auth_manager
        mgr = get_auth_manager()
        if not mgr.is_token_valid():
            logger.error(
                "[ERROR] Dhan token EXPIRED — Go to web.dhan.co -> My Profile -> "
                "Access DhanHQ APIs -> Generate Token -> Update DHAN_ACCESS_TOKEN in .env"
            )
        else:
            logger.info("[OK] Dhan token valid on startup")
    except Exception as e:
        logger.warning(f"Startup token check: {e}")
    yield


app = FastAPI(
    title="Algo Trading Platform",
    version="1.0.0",
    docs_url="/api/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_ops_metrics()
Instrumentator().instrument(app).expose(app)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(brokers.router, prefix="/api/brokers", tags=["Brokers"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["Strategies"])
app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
app.include_router(websocket.router, prefix="/api/ws", tags=["WebSocket"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(signals.router, prefix="/api/signals", tags=["CopyTrading"])
app.include_router(risk.router, prefix="/api/risk", tags=["Risk"])
app.include_router(options.router, prefix="/api/options", tags=["Options"])
app.include_router(market.router, prefix="/api/market", tags=["Market"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["Backtest"])
app.include_router(formula.router, prefix="/api/formula", tags=["Formula"])
app.include_router(terminal.router, prefix="/api/terminal", tags=["Terminal"])
app.include_router(copy_trading.router, prefix="/api/copy-trading", tags=["DhanCopyTrading"])
app.include_router(dhan_auth_router, prefix="/api")
app.include_router(settings_router, prefix="/api")



@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "live_trading_enabled": settings.LIVE_TRADING_ENABLED,
    }


# ── Serve Built Frontend SPA (Standalone Mode) ────────────────────────────────
import os
import sys
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException


def _find_frontend_dist() -> str:
    candidates = []
    # If running inside PyInstaller bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "frontend", "dist"))
    # If running alongside the frozen executable
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "frontend", "dist"))
        candidates.append(os.path.join(exe_dir, "dist"))
    # Standard development relative paths
    candidates.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")))
    candidates.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")))
    candidates.append(os.path.abspath(os.path.join(os.getcwd(), "frontend", "dist")))

    for path in candidates:
        if os.path.exists(os.path.join(path, "index.html")):
            return path
    return ""


_frontend_dist = _find_frontend_dist()
if _frontend_dist and os.path.exists(_frontend_dist):
    _assets_dir = os.path.join(_frontend_dist, "assets")
    if os.path.exists(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("metrics"):
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = os.path.join(_frontend_dist, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        index_file = os.path.join(_frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend index.html not found")

