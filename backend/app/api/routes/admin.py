"""
Admin Routes — full platform management console.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.broker import BrokerAccount
from app.models.strategy import Strategy, UserStrategyMap, StrategyStatus
from app.models.trade import Trade
from app.models.signal import Signal

router = APIRouter()


# ── Platform overview ─────────────────────────────────────────────────────────

@router.get("/overview")
async def platform_overview(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users     = (await db.execute(select(func.count(User.id)))).scalar()
    active_users    = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar()
    total_trades    = (await db.execute(select(func.count(Trade.id)))).scalar()
    paper_trades    = (await db.execute(select(func.count(Trade.id)).where(Trade.is_paper == True))).scalar()
    live_trades     = total_trades - paper_trades
    total_strategies= (await db.execute(select(func.count(Strategy.id)))).scalar()
    active_maps     = (await db.execute(
        select(func.count(UserStrategyMap.id)).where(UserStrategyMap.status == StrategyStatus.active)
    )).scalar()
    total_signals   = (await db.execute(select(func.count(Signal.id)))).scalar()

    return {
        "users":            {"total": total_users,     "active": active_users},
        "trades":           {"total": total_trades,    "paper": paper_trades, "live": live_trades},
        "strategies":       {"total": total_strategies,"active_assignments": active_maps},
        "signals":          {"total": total_signals},
    }


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users  = result.scalars().all()
    out = []
    for u in users:
        brokers = (await db.execute(
            select(func.count(BrokerAccount.id)).where(BrokerAccount.user_id == u.id)
        )).scalar()
        strategies = (await db.execute(
            select(func.count(UserStrategyMap.id)).where(UserStrategyMap.user_id == u.id)
        )).scalar()
        trades = (await db.execute(
            select(func.count(Trade.id)).where(Trade.user_id == u.id)
        )).scalar()
        out.append({
            "id":          str(u.id),
            "email":       u.email,
            "username":    u.username,
            "role":        u.role,
            "is_active":   u.is_active,
            "mfa_enabled": u.mfa_enabled,
            "created_at":  u.created_at.isoformat() if u.created_at else None,
            "brokers":     brokers,
            "strategies":  strategies,
            "trades":      trades,
        })
    return out


class CreateUserRequest(BaseModel):
    email:    str
    username: str
    password: str
    role:     str = "trader"


@router.post("/users", status_code=201)
async def create_user(
    payload: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(
        email           = payload.email,
        username        = payload.username,
        hashed_password = hash_password(payload.password),
        role            = UserRole.admin if payload.role == "admin" else UserRole.trader,
        is_active       = True,
    )
    db.add(user)
    await db.commit()
    return {"id": str(user.id), "username": user.username}


@router.patch("/users/{user_id}/toggle")
async def toggle_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    await db.commit()
    return {"is_active": user.is_active}


@router.patch("/users/{user_id}/role")
async def change_role(
    user_id: UUID,
    role: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = UserRole.admin if role == "admin" else UserRole.trader
    await db.commit()
    return {"role": user.role}


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user_id) == str(admin.id):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    await db.delete(user)
    await db.commit()


# ── Strategy management ───────────────────────────────────────────────────────

class CreateStrategyRequest(BaseModel):
    name:           str
    description:    str
    engine_class:   str
    default_params: dict = {}


@router.get("/strategies")
async def list_all_strategies(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Strategy).order_by(Strategy.created_at.desc()))
    strats = result.scalars().all()
    return [
        {
            "id":            str(s.id),
            "name":          s.name,
            "description":   s.description,
            "engine_class":  s.engine_class,
            "default_params":s.default_params,
            "is_available":  s.is_available,
        }
        for s in strats
    ]


@router.post("/strategies", status_code=201)
async def create_strategy(
    payload: CreateStrategyRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    s = Strategy(
        name           = payload.name,
        description    = payload.description,
        engine_class   = payload.engine_class,
        default_params = payload.default_params,
        is_available   = True,
    )
    db.add(s)
    await db.commit()
    return {"id": str(s.id), "name": s.name}


@router.patch("/strategies/{strategy_id}/toggle")
async def toggle_strategy(
    strategy_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    s = await db.get(Strategy, strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="Strategy not found")
    s.is_available = not s.is_available
    await db.commit()
    return {"is_available": s.is_available}


# ── Assign strategy to user ───────────────────────────────────────────────────

class AssignRequest(BaseModel):
    user_id:           UUID
    strategy_id:       UUID
    broker_account_id: UUID
    params:            dict = {}
    paper_trading:     bool = True


@router.post("/assign-strategy", status_code=201)
async def admin_assign_strategy(
    payload: AssignRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    usm = UserStrategyMap(
        user_id           = payload.user_id,
        strategy_id       = payload.strategy_id,
        broker_account_id = payload.broker_account_id,
        params            = payload.params,
        paper_trading     = payload.paper_trading,
        status            = StrategyStatus.stopped,
    )
    db.add(usm)
    await db.commit()
    return {"id": str(usm.id)}


# ── All trades ────────────────────────────────────────────────────────────────

@router.get("/trades")
async def all_trades(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
):
    result = await db.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "id":         str(t.id),
            "user_id":    str(t.user_id),
            "symbol":     t.symbol,
            "exchange":   t.exchange,
            "direction":  t.direction,
            "quantity":   t.quantity,
            "entry_price":t.entry_price,
            "pnl":        t.pnl,
            "status":     t.status,
            "is_paper":   t.is_paper,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in trades
    ]
