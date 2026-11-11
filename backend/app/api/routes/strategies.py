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
from app.market.dhan_feed import redis_exchange

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
    order_fields = {"symbol", "quantity", "exchange"}
    is_admin = current_user.role == "admin"
    return [
        {
            "id":             str(s.id),
            "name":           s.name,
            "description":    s.description,
            "default_params": s.default_params if is_admin else {
                key: value
                for key, value in (s.default_params or {}).items()
                if key in order_fields
            },
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
    """Assign a strategy to the broker account's user. It runs on that user's whole watchlist."""
    account = await db.get(BrokerAccount, payload.broker_account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Broker account not found")
    if account.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    strat = await db.get(Strategy, payload.strategy_id)
    if not strat or not strat.is_available:
        raise HTTPException(status_code=404, detail="Strategy not found")

    from app.models.watchlist import UserWatchlist
    listed = await db.execute(
        select(UserWatchlist).where(UserWatchlist.user_id == account.user_id)
    )
    symbols = [
        {"symbol": row.symbol, "token": row.security_id, "exchange": redis_exchange(row.exchange_segment)}
        for row in listed.scalars().all()
    ]
    if not symbols:
        raise HTTPException(status_code=400, detail="Add symbols on the terminal watchlist before assigning a strategy")

    params = dict(payload.params or {})
    params.pop("symbol", None)
    params["apply_to"] = "watchlist"
    params["symbols"] = [row["symbol"] for row in symbols]
    reason = _live_block(strat, payload.paper_trading, params, None, require_params=False)
    if reason:
        raise HTTPException(status_code=403, detail=reason)

    usm = UserStrategyMap(
        user_id           = account.user_id,
        strategy_id       = payload.strategy_id,
        broker_account_id = payload.broker_account_id,
        params            = params,
        engine_version    = strat.version,
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

    from app.models.watchlist import UserWatchlist
    listed = await db.execute(
        select(UserWatchlist).where(UserWatchlist.user_id == usm.user_id)
    )
    watch = list(listed.scalars().all())
    if not watch:
        raise HTTPException(status_code=400, detail="The watchlist is empty")
    symbols = [row.symbol.upper() for row in watch]

    if not usm.paper_trading:
        # Live path — hard gates before mutating state or enqueueing work
        from app.core.trading_mode import LiveTradingError, assert_live_allowed, require_not_killed
        try:
            assert_live_allowed()
            await require_not_killed()
        except LiveTradingError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)

    strat = await db.get(Strategy, usm.strategy_id)
    reason = _live_block(strat, usm.paper_trading, usm.params or {}, usm.engine_version, require_params=True)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    if not usm.paper_trading and strat is not None:
        from app.strategy.backtest_runner import backtest_block_reason
        from app.models.backtest import BacktestRun
        latest = await db.execute(
            select(BacktestRun)
            .where(
                BacktestRun.engine_class == strat.engine_class,
                BacktestRun.version == (strat.version or "1"),
                BacktestRun.symbol.in_(symbols),
            )
            .order_by(BacktestRun.created_at.desc())
        )
        seen = set()
        for row in latest.scalars().all():
            key = row.symbol.upper()
            if key in seen:
                continue
            seen.add(key)
            blocked = backtest_block_reason(bool(row.passed))
            if blocked:
                raise HTTPException(status_code=403, detail=f"{key}: {blocked}")

    usm.status = StrategyStatus.active
    await db.commit()

    if usm.paper_trading:
        from app.worker.tasks import start_simulated_feed
        price = float(usm.params.get("base_price", 2800.0))
        for row in watch:
            exch = redis_exchange(row.exchange_segment)
            start_simulated_feed.delay(exchange=exch, token=row.security_id, base_price=price)
        logger.info("Paper trading: simulated feed started for %s symbols", len(watch))
    else:
        from app.worker.tasks import start_dhan_feed
        start_dhan_feed.delay(instruments=[
            {
                "exchange": redis_exchange(row.exchange_segment),
                "security_id": row.security_id,
                "token": row.security_id,
            }
            for row in watch
        ])
        logger.info("Live trading: Dhan feed started for %s symbols", len(watch))

    from app.worker.tasks import run_strategy
    task = run_strategy.delay(str(map_id))

    return {
        "status":     "started",
        "task_id":    task.id,
        "feed":       "simulated" if usm.paper_trading else "dhan_live",
        "symbols":    [row.symbol for row in watch],
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
    """Remove a strategy assignment. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
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
    """Admin only: add a new strategy to the catalogue. Live stays off until enable-live."""
    from app.strategy.registry import get_strategy_class
    try:
        cls = get_strategy_class(payload.engine_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    s = Strategy(
        name          = payload.name,
        description   = payload.description,
        engine_class  = payload.engine_class,
        default_params= payload.default_params,
        version       = cls.version,
        live_enabled  = False,
        warmup_bars   = cls.warmup_bars,
        max_positions = cls.max_positions,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return {"id": str(s.id), "name": s.name, "version": s.version, "live_enabled": False}


@router.post("/admin/{strategy_id}/enable-live")
async def enable_live_strategy(
    strategy_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin: allow this catalogue version to be assigned and started live."""
    from app.strategy.registry import get_strategy_class

    strat = await db.get(Strategy, strategy_id)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        cls = get_strategy_class(strat.engine_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if cls.version != (strat.version or "1"):
        raise HTTPException(
            status_code=409,
            detail=f"Loaded engine is version {cls.version}; catalogue row is {strat.version}",
        )
    strat.live_enabled = True
    strat.version = cls.version
    await db.commit()
    return {"id": str(strat.id), "version": strat.version, "live_enabled": True}


def _live_block(strat: Strategy, paper: bool, params: dict, pinned: str | None, require_params: bool) -> str | None:
    from app.strategy.exits import live_start_block_reason
    from app.strategy.registry import get_strategy_class

    if strat is None:
        return "Strategy not found"
    try:
        cls = get_strategy_class(strat.engine_class)
    except ValueError as exc:
        return str(exc)
    params_ok = True
    if require_params:
        try:
            params_ok = bool(cls(params).validate_params())
        except Exception:
            params_ok = False
    return live_start_block_reason(
        paper=paper,
        live_enabled=bool(strat.live_enabled),
        catalogue_version=strat.version or cls.version,
        code_version=cls.version,
        pinned_version=pinned,
        params_ok=params_ok,
    )


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


@router.get("/all-assignments")
async def get_all_assignments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin only — list all strategy assignments across all users."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from sqlalchemy import select
    from app.models.strategy import UserStrategyMap, Strategy
    from app.models.user import User as UserModel
    from app.models.broker import BrokerAccount

    result = await db.execute(
        select(UserStrategyMap, Strategy, UserModel, BrokerAccount)
        .join(Strategy,      Strategy.id      == UserStrategyMap.strategy_id)
        .join(UserModel,     UserModel.id     == UserStrategyMap.user_id)
        .join(BrokerAccount, BrokerAccount.id == UserStrategyMap.broker_account_id)
        .order_by(UserStrategyMap.created_at.desc())
    )
    rows = result.all()

    return [
        {
            "id":            str(usm.id),
            "user_id":       str(usm.user_id),
            "username":      user.username,
            "strategy_name": strat.name,
            "broker":        f"{broker.broker.value} ({'PAPER' if broker.paper_trading else 'LIVE'})",
            "status":        usm.status,
            "paper_trading": usm.paper_trading,
        }
        for usm, strat, user, broker in rows
    ]


@router.get("/live-signals")
async def get_live_signals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluate all assigned strategies against current tick data.
    Returns signal per strategy per symbol for the terminal.
    """
    from sqlalchemy import select
    from app.models.strategy import UserStrategyMap, Strategy
    from app.core.config import settings
    from app.strategy.registry import get_strategy_class
    import pandas as pd, httpx, os
    from datetime import datetime
    import pytz

    # Get user's assigned strategies
    result = await db.execute(
        select(UserStrategyMap, Strategy)
        .join(Strategy, Strategy.id == UserStrategyMap.strategy_id)
        .where(
            UserStrategyMap.user_id == current_user.id,
            UserStrategyMap.status.in_(["stopped", "active", "paused"]),
        )
    )
    assignments = result.all()
    if not assignments:
        return []

    # Get current watchlist symbols + live ticks from Redis/MarketPoller
    from app.models.watchlist import UserWatchlist
    wl_result = await db.execute(
        select(UserWatchlist).where(UserWatchlist.user_id == current_user.id)
    )
    watchlist = wl_result.scalars().all()
    if not watchlist:
        return []

    # Get live tick data from market poller
    from app.market.market_poller import get_poller
    poller    = get_poller()
    # _last_data is a list of tick dicts — convert to symbol-keyed dict
    _raw      = getattr(poller, '_last_data', []) or []
    live_data = {t["symbol"]: t for t in _raw if "symbol" in t}

    signals = []
    IST     = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(IST)

    for usm, strategy in assignments:
        try:
            StrategyClass = get_strategy_class(strategy.engine_class)

            for wl in watchlist:
                sym  = wl.symbol
                tick = live_data.get(sym, {})
                if not tick:
                    continue
                params = {
                    **(usm.params or strategy.default_params or {}),
                    "symbol": sym,
                    "exchange": redis_exchange(wl.exchange_segment),
                    "token": wl.security_id,
                }
                engine = StrategyClass(params)

                ltp   = float(tick.get("ltp",   0) or 0)
                open_ = float(tick.get("open",  0) or 0)
                high  = float(tick.get("high",  0) or 0)
                low   = float(tick.get("low",   0) or 0)
                close = float(tick.get("close", 0) or 0)

                if not ltp:
                    continue

                # Build minimal OHLCV dataframe for strategy
                df = pd.DataFrame([{
                    "open":   open_,
                    "high":   high,
                    "low":    low,
                    "close":  close,
                    "volume": int(tick.get("volume", 0) or 0),
                    "datetime": now_ist,
                }])

                try:
                    signal = engine.generate_signal(df, ltp=ltp)
                except TypeError:
                    signal = engine.generate_signal(df)

                signals.append({
                    "assignment_id":  str(usm.id),
                    "strategy_id":    str(strategy.id),
                    "strategy_name":  strategy.name,
                    "symbol":         sym,
                    "direction":      signal.direction if signal else "HOLD",
                    "price":          signal.price     if signal else ltp,
                    "sl":             signal.sl        if signal else None,
                    "target":         signal.target    if signal else None,
                    "paper_trading":  usm.paper_trading,
                })
        except Exception as e:
            logger.warning(f"Signal eval error for {strategy.name}: {e}")
            continue

    return signals
