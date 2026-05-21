from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.database import init_db
from app.api.routes import (
    auth, users, brokers, strategies, trades,
    websocket, admin, signals, risk, market, backtest, formula, terminal
)
import app.models  # noqa


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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

app.include_router(auth.router,       prefix="/api/auth",       tags=["Auth"])
app.include_router(users.router,      prefix="/api/users",      tags=["Users"])
app.include_router(brokers.router,    prefix="/api/brokers",    tags=["Brokers"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["Strategies"])
app.include_router(trades.router,     prefix="/api/trades",     tags=["Trades"])
app.include_router(websocket.router,  prefix="/api/ws",         tags=["WebSocket"])
app.include_router(admin.router,      prefix="/api/admin",      tags=["Admin"])
app.include_router(signals.router,    prefix="/api/signals",    tags=["CopyTrading"])
app.include_router(risk.router,       prefix="/api/risk",       tags=["Risk"])
app.include_router(market.router,     prefix="/api/market",     tags=["Market"])
app.include_router(backtest.router,   prefix="/api/backtest",   tags=["Backtest"])
app.include_router(formula.router,    prefix="/api/formula",    tags=["Formula"])
app.include_router(terminal.router,   prefix="/api/terminal",   tags=["Terminal"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
