"""
Strategy routes — Phase 4
Assigns strategies to users and starts/stops execution via Celery.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
import json
import logging

from app.core.database import get_db

logger = logging.getLogger(__name__)
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.models.strategy import Strategy, UserStrategyMap, StrategyStatus
from app.models.broker import BrokerAccount
from app.core.redis_client import get_redis, strategy_running_key, strategy_state_key

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class StrategyListItem(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    default_params: dict
    is_available: bool

    class Config:
        from_attributes = True


class AssignStrategyRequest(BaseModel):
    strategy_id: UUID
    broker_account_id: UUID
    params: dict = {}
    paper_trading: bool = True


class StrategyMapResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    strategy_name: str
    broker_account_id: UUID
    params: dict
    status: str
    paper_trading: bool

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_available_strategies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all strategies available to the user (engine_class is never returned)."""
    result = await db.execute(
        select(Strategy).where(Strategy.is_available == True)
    )
    strategies = result.scalars().all()
    return [
        {
            "id":             str(s.id),
            "name":           s.name,
            "description":    s.description,
            "default_params": s.default_params,
        }
        for s in strategies
    ]


@router.get("/my")
async def my_strategies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's assigned strategies with live runtime status."""
    result = await db.execute(
        select(UserStrategyMap, Strategy)
        .join(Strategy, UserStrategyMap.strategy_id == Strategy.id)
        .where(UserStrategyMap.user_id == current_user.id)
    )
    rows = result.all()
    redis = get_redis()

    out = []
    for usm, strat in rows:
        # Fetch live state from Redis
        raw = await redis.get(strategy_state_key(str(usm.id)))
        runtime = json.loads(raw) if raw else {}

        out.append({
            "id":               str(usm.id),
            "strategy_id":      str(strat.id),
            "strategy_name":    strat.name,
            "broker_account_id":str(usm.broker_account_id),
            "params":           usm.params,
            "status":           usm.status,
            "paper_trading":    usm.paper_trading,
            "daily_pnl":        runtime.get("daily_pnl", 0),
            "killed":           runtime.get("killed", False),
        })
    return out


@router.post("/assign", status_code=201)
async def assign_strategy(
    payload: AssignStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a strategy to the user with a specific broker account."""
    # Verify broker account belongs to user
    ba = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.id == payload.broker_account_id,
            BrokerAccount.user_id == current_user.id,
        )
    )
    if not ba.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Broker account not found")

    usm = UserStrategyMap(
        user_id           = current_user.id,
        strategy_id       = payload.strategy_id,
        broker_account_id = payload.broker_account_id,
        params            = payload.params,
        paper_trading     = payload.paper_trading,
        status            = StrategyStatus.stopped,
    )
    db.add(usm)
    await db.commit()
    await db.refresh(usm)
    return {"id": str(usm.id), "status": usm.status}


@router.post("/{map_id}/start")
async def start_strategy(
    map_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start strategy execution via Celery worker."""
    usm = await _get_usm(map_id, current_user.id, db)

    if usm.status == StrategyStatus.active:
        raise HTTPException(status_code=400, detail="Strategy is already running")

    usm.status = StrategyStatus.active
    await db.commit()

    symbol   = usm.params.get("symbol", "RELIANCE")
    exchange = usm.params.get("exchange", "NSE")
    token    = usm.params.get("token", "2885")

    if usm.paper_trading:
        # Paper trading — use simulated feed
        from app.worker.tasks import start_simulated_feed
        price = float(usm.params.get("base_price", 2800.0))
        start_simulated_feed.delay(exchange=exchange, token=token, base_price=price)
        logger.info(f"Paper trading: simulated feed started for {symbol}")
    else:
        # Live trading — use Dhan real-time feed
        from app.worker.tasks import start_dhan_feed
        from app.core.config import settings
        if not settings.DHAN_CLIENT_ID or not settings.DHAN_ACCESS_TOKEN:
            raise HTTPException(
                status_code=400,
                detail="DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN not set in .env"
            )
        start_dhan_feed.delay(instruments=[{
            "exchange":    exchange,
            "security_id": token,
            "token":       token,
        }])
        logger.info(f"Live trading: Dhan feed started for {symbol} ({exchange}:{token})")

    # Launch strategy executor
    from app.worker.tasks import run_strategy
    task = run_strategy.delay(str(map_id))

    return {
        "status":     "started",
        "task_id":    task.id,
        "feed":       "simulated" if usm.paper_trading else "dhan_live",
        "symbol":     symbol,
        "exchange":   exchange,
    }


@router.post("/{map_id}/stop")
async def stop_strategy(
    map_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop a running strategy."""
    usm = await _get_usm(map_id, current_user.id, db)

    usm.status = StrategyStatus.stopped
    await db.commit()

    from app.worker.tasks import stop_strategy as _stop
    _stop.delay(str(map_id))

    return {"status": "stopped"}


@router.delete("/{map_id}")
async def remove_strategy(
    map_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a strategy assignment."""
    usm = await _get_usm(map_id, current_user.id, db)
    if usm.status == StrategyStatus.active:
        raise HTTPException(status_code=400, detail="Stop the strategy before removing")
    await db.delete(usm)
    await db.commit()
    return {"status": "removed"}


# ── Admin: manage strategy catalogue ─────────────────────────────────────────

class CreateStrategyRequest(BaseModel):
    name: str
    description: str
    engine_class: str
    default_params: dict = {}


@router.post("/admin/create", status_code=201)
async def create_strategy(
    payload: CreateStrategyRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin only: add a new strategy to the catalogue."""
    s = Strategy(
        name          = payload.name,
        description   = payload.description,
        engine_class  = payload.engine_class,
        default_params= payload.default_params,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return {"id": str(s.id), "name": s.name}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_usm(map_id: UUID, user_id, db: AsyncSession) -> UserStrategyMap:
    result = await db.execute(
        select(UserStrategyMap).where(
            UserStrategyMap.id == map_id,
            UserStrategyMap.user_id == user_id,
        )
    )
    usm = result.scalar_one_or_none()
    if not usm:
        raise HTTPException(status_code=404, detail="Strategy assignment not found")
    return usm
