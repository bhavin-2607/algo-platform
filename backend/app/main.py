from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logging
logger = logging.getLogger(__name__)
from app.core.config import settings
from app.core.database import init_db
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
                "❌ Dhan token EXPIRED — Go to web.dhan.co → My Profile → "
                "Access DhanHQ APIs → Generate Token → Update DHAN_ACCESS_TOKEN in .env"
            )
        else:
            logger.info("✅ Dhan token valid on startup")
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(dhan_auth_router, prefix="/api")
app.include_router(settings_router, prefix="/api")



@app.get("/api/health")
async def health():
    return {"status": "ok"}
