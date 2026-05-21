"""
Risk Management Routes — Phase 7
Provides read/write access to risk settings and live runtime state per strategy.
Also exposes the emergency kill switch.
"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.redis_client import get_redis, strategy_state_key, strategy_running_key
from app.models.user import User
from app.models.strategy import UserStrategyMap
from app.models.risk import RiskSettings, RiskEvent

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RiskSettingsSchema(BaseModel):
    daily_loss_limit:       float = 2000.0
    max_exposure:           float = 50000.0
    max_quantity:           int   = 10
    max_consecutive_losses: int   = 3

    class Config:
        from_attributes = True


class RiskSettingsResponse(RiskSettingsSchema):
    id:                   str
    user_strategy_map_id: str
    kill_switch_active:   bool
    updated_at:           Optional[str]

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{map_id}")
async def get_risk_settings(
    map_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get risk settings + live runtime state for a strategy."""
    await _verify_ownership(map_id, current_user.id, db)

    settings = await _get_or_create_settings(map_id, db)

    # Fetch live runtime state from Redis
    redis = get_redis()
    raw = await redis.get(strategy_state_key(str(map_id)))
    runtime = json.loads(raw) if raw else {}

    return {
        "id":                    str(settings.id),
        "user_strategy_map_id":  str(settings.user_strategy_map_id),
        "daily_loss_limit":      settings.daily_loss_limit,
        "max_exposure":          settings.max_exposure,
        "max_quantity":          settings.max_quantity,
        "max_consecutive_losses":settings.max_consecutive_losses,
        "kill_switch_active":    settings.kill_switch_active,
        "updated_at":            settings.updated_at.isoformat() if settings.updated_at else None,
        # Live runtime (from Redis)
        "runtime": {
            "status":             runtime.get("status", "stopped"),
            "daily_pnl":          runtime.get("daily_pnl", 0.0),
            "consecutive_losses": runtime.get("consecutive_losses", 0),
            "killed":             runtime.get("killed", False),
        }
    }


@router.put("/{map_id}")
async def update_risk_settings(
    map_id: UUID,
    payload: RiskSettingsSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update risk limits for a strategy. Takes effect on next tick."""
    await _verify_ownership(map_id, current_user.id, db)
    settings = await _get_or_create_settings(map_id, db)

    settings.daily_loss_limit       = payload.daily_loss_limit
    settings.max_exposure           = payload.max_exposure
    settings.max_quantity           = payload.max_quantity
    settings.max_consecutive_losses = payload.max_consecutive_losses

    # Log the change
    db.add(RiskEvent(
        user_id    = current_user.id,
        map_id     = map_id,
        event_type = "limit_changed",
        reason     = f"DLL={payload.daily_loss_limit} EXP={payload.max_exposure} QTY={payload.max_quantity}",
    ))
    await db.commit()

    # Push updated limits to Redis so running executor picks them up
    redis = get_redis()
    await redis.set(
        f"risk_config:{map_id}",
        json.dumps({
            "daily_loss_limit":       payload.daily_loss_limit,
            "max_exposure":           payload.max_exposure,
            "max_quantity":           payload.max_quantity,
            "max_consecutive_losses": payload.max_consecutive_losses,
        }),
        ex=86400,
    )

    return {"status": "updated"}


@router.post("/{map_id}/kill")
async def activate_kill_switch(
    map_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Emergency kill switch — immediately stops all trading for this strategy."""
    await _verify_ownership(map_id, current_user.id, db)
    settings = await _get_or_create_settings(map_id, db)

    settings.kill_switch_active = True

    # Signal the running executor to stop
    redis = get_redis()
    await redis.delete(strategy_running_key(str(map_id)))
    await redis.publish(f"strategy_status:{map_id}", json.dumps({
        "map_id": str(map_id),
        "status": "killed",
        "killed": True,
        "daily_pnl": 0,
        "consecutive_losses": 0,
    }))

    # Update DB strategy status
    usm = await db.get(UserStrategyMap, map_id)
    if usm:
        from app.models.strategy import StrategyStatus
        usm.status = StrategyStatus.stopped

    db.add(RiskEvent(
        user_id    = current_user.id,
        map_id     = map_id,
        event_type = "killed",
        reason     = "Manual kill switch activated",
    ))
    await db.commit()

    logger.warning(f"Kill switch activated: map={map_id} user={current_user.id}")
    return {"status": "killed", "message": "Strategy stopped immediately"}


@router.post("/{map_id}/reset")
async def reset_kill_switch(
    map_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset the kill switch and daily counters so the strategy can be restarted."""
    await _verify_ownership(map_id, current_user.id, db)
    settings = await _get_or_create_settings(map_id, db)
    settings.kill_switch_active = False

    # Clear Redis runtime state
    redis = get_redis()
    await redis.delete(strategy_state_key(str(map_id)))

    db.add(RiskEvent(
        user_id    = current_user.id,
        map_id     = map_id,
        event_type = "reset",
        reason     = "Manual reset",
    ))
    await db.commit()

    return {"status": "reset", "message": "Kill switch cleared. You can restart the strategy."}


@router.get("/{map_id}/events")
async def get_risk_events(
    map_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Audit log of risk events for a strategy."""
    await _verify_ownership(map_id, current_user.id, db)

    result = await db.execute(
        select(RiskEvent)
        .where(RiskEvent.map_id == map_id)
        .order_by(RiskEvent.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            "id":         str(e.id),
            "event_type": e.event_type,
            "reason":     e.reason,
            "value":      e.value,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.get("/overview/all")
async def risk_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Summary of risk state across all user's strategies.
    Used by the Risk Management dashboard.
    """
    result = await db.execute(
        select(UserStrategyMap)
        .where(UserStrategyMap.user_id == current_user.id)
    )
    maps = result.scalars().all()

    redis = get_redis()
    overview = []

    for usm in maps:
        settings = await _get_or_create_settings(usm.id, db)
        raw      = await redis.get(strategy_state_key(str(usm.id)))
        runtime  = json.loads(raw) if raw else {}

        daily_pnl   = runtime.get("daily_pnl", 0.0)
        killed      = runtime.get("killed", False) or settings.kill_switch_active
        pnl_pct     = abs(daily_pnl / settings.daily_loss_limit * 100) if settings.daily_loss_limit else 0

        overview.append({
            "map_id":               str(usm.id),
            "status":               usm.status,
            "paper_trading":        usm.paper_trading,
            "daily_pnl":            round(daily_pnl, 2),
            "daily_loss_limit":     settings.daily_loss_limit,
            "pnl_used_pct":         round(min(pnl_pct, 100), 1),
            "max_quantity":         settings.max_quantity,
            "max_exposure":         settings.max_exposure,
            "consecutive_losses":   runtime.get("consecutive_losses", 0),
            "max_consecutive_losses":settings.max_consecutive_losses,
            "kill_switch_active":   killed,
        })

    return overview


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _verify_ownership(map_id: UUID, user_id, db: AsyncSession):
    result = await db.execute(
        select(UserStrategyMap).where(
            UserStrategyMap.id      == map_id,
            UserStrategyMap.user_id == user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Strategy not found")


async def _get_or_create_settings(map_id: UUID, db: AsyncSession) -> RiskSettings:
    result = await db.execute(
        select(RiskSettings).where(RiskSettings.user_strategy_map_id == map_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = RiskSettings(user_strategy_map_id=map_id)
        db.add(settings)
        await db.flush()
    return settings
