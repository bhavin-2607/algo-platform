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
    from app.models.algo_row import BsaAlgoRow
    from app.broker.dhan import get_public_ipv4

    total_users     = (await db.execute(select(func.count(User.id)))).scalar()
    active_users    = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar()
    total_trades    = (await db.execute(select(func.count(Trade.id)))).scalar()
    paper_trades    = (await db.execute(select(func.count(Trade.id)).where(Trade.is_paper == True))).scalar()
    live_trades     = total_trades - paper_trades
    total_algo_scripts = (await db.execute(select(func.count(BsaAlgoRow.id)))).scalar()
    active_algo_scripts = (await db.execute(select(func.count(BsaAlgoRow.id)).where(BsaAlgoRow.is_algo_active == True))).scalar()
    server_ip = get_public_ipv4()

    return {
        "users":            {"total": total_users,     "active": active_users},
        "trades":           {"total": total_trades,    "paper": paper_trades, "live": live_trades},
        "algo":             {"total": total_algo_scripts, "active": active_algo_scripts},
        "server_ip":        server_ip,
    }


# ── Dhan IP Whitelisting & Verification ───────────────────────────────────────

class WhitelistDhanIpPayload(BaseModel):
    ip: Optional[str] = None
    ip_flag: str = "PRIMARY"


async def _get_active_dhan_credentials(db: AsyncSession) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Helper to fetch Dhan client_id, access_token, and account name."""
    from app.core.config import settings
    from app.core.security import decrypt_broker_token

    result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.broker == "DHAN",
            BrokerAccount.is_active == True,
        )
    )
    accounts = result.scalars().all()
    master = next((a for a in accounts if a.account_role == "MASTER"), None) or (accounts[0] if accounts else None)

    client_id = (master.client_id if master else "") or getattr(settings, "DHAN_CLIENT_ID", "")
    token = getattr(settings, "DHAN_ACCESS_TOKEN", "")
    if master and master.encrypted_access_token:
        try:
            token = decrypt_broker_token(master.encrypted_access_token)
        except Exception:
            pass
    account_name = master.account_name if master else "Dhan Master"
    return client_id, token, account_name


@router.get("/dhan-ip")
async def get_dhan_ip_verification(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Check current server public IPv4 against Dhan configured static IP.
    Calls Dhan v2 /ip/getIP endpoint using active broker credentials.
    """
    import requests
    from app.broker.dhan import get_public_ipv4

    server_ip = get_public_ipv4()
    client_id, token, account_name = await _get_active_dhan_credentials(db)

    if not client_id or not token:
        return {
            "current_server_ip": server_ip,
            "dhan_primary_ip": None,
            "dhan_secondary_ip": None,
            "is_matched": False,
            "modify_eligible_date": None,
            "client_id": client_id or "Not configured",
            "account_name": account_name,
            "status": "NO_CREDENTIALS",
            "message": "Dhan credentials (Client ID or Access Token) not found. Please link Dhan in Broker settings.",
        }

    # Query Dhan API
    url = "https://api.dhan.co/v2/ip/getIP"
    headers = {
        "access-token": token,
        "client-id": client_id,
        "dhanClientId": client_id,
        "Accept": "application/json",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            body = data.get("data") if isinstance(data.get("data"), dict) else data
            primary_ip = str(body.get("primaryIp") or body.get("ip") or "").strip()
            secondary_ip = str(body.get("secondaryIp") or "").strip()
            eligible_date = body.get("modifyEligibleDate") or body.get("eligibleDate")

            is_matched = bool(server_ip and server_ip != "unknown" and (server_ip == primary_ip or server_ip == secondary_ip))
            return {
                "current_server_ip": server_ip,
                "dhan_primary_ip": primary_ip or None,
                "dhan_secondary_ip": secondary_ip or None,
                "is_matched": is_matched,
                "modify_eligible_date": eligible_date,
                "client_id": client_id,
                "account_name": account_name,
                "status": "SUCCESS",
                "message": "IP configuration verified successfully." if is_matched else "Server IP does not match Dhan whitelisted IP.",
            }
        else:
            err_msg = resp.text
            try:
                err_json = resp.json()
                err_msg = err_json.get("remarks") or err_json.get("errorMessage") or err_msg
            except Exception:
                pass
            return {
                "current_server_ip": server_ip,
                "dhan_primary_ip": None,
                "dhan_secondary_ip": None,
                "is_matched": False,
                "modify_eligible_date": None,
                "client_id": client_id,
                "account_name": account_name,
                "status": "DHAN_ERROR",
                "message": f"Dhan API returned {resp.status_code}: {err_msg}",
            }
    except Exception as e:
        return {
            "current_server_ip": server_ip,
            "dhan_primary_ip": None,
            "dhan_secondary_ip": None,
            "is_matched": False,
            "modify_eligible_date": None,
            "client_id": client_id,
            "account_name": account_name,
            "status": "ERROR",
            "message": f"Could not connect to Dhan: {str(e)}",
        }


@router.post("/dhan-ip/whitelist")
async def whitelist_dhan_ip(
    payload: WhitelistDhanIpPayload,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Whitelist or update static IP on Dhan directly using access token via PUT /v2/ip/modifyIP.
    """
    import requests
    from app.broker.dhan import get_public_ipv4

    target_ip = (payload.ip or "").strip()
    if not target_ip:
        target_ip = get_public_ipv4()

    if not target_ip or target_ip == "unknown" or "." not in target_ip:
        raise HTTPException(status_code=400, detail="Invalid IPv4 address")

    client_id, token, account_name = await _get_active_dhan_credentials(db)
    if not client_id or not token:
        raise HTTPException(status_code=400, detail="Active Dhan credentials not found")

    url = "https://api.dhan.co/v2/ip/modifyIP"
    headers = {
        "access-token": token,
        "client-id": client_id,
        "dhanClientId": client_id,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "dhanClientId": client_id,
        "ip": target_ip,
        "ipFlag": payload.ip_flag.upper(),
    }

    try:
        resp = requests.put(url, headers=headers, json=body, timeout=8)
        if resp.status_code in (200, 201):
            data = resp.json()
            return {
                "success": True,
                "message": f"IP {target_ip} ({payload.ip_flag.upper()}) whitelisted on Dhan successfully",
                "target_ip": target_ip,
                "dhan_response": data,
            }
        else:
            err_msg = resp.text
            try:
                err_json = resp.json()
                err_msg = err_json.get("remarks") or err_json.get("errorMessage") or err_msg
            except Exception:
                pass
            raise HTTPException(status_code=resp.status_code, detail=f"Dhan IP Whitelisting failed: {err_msg}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error connecting to Dhan modifyIP: {str(e)}")


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


class ResetPasswordRequest(BaseModel):
    password: str


@router.patch("/users/{user_id}/password")
async def reset_user_password(
    user_id: UUID,
    payload: ResetPasswordRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set a new password when the current one is unknown. Admin only."""
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(payload.password)
    await db.commit()
    return {"message": "Password reset"}


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
            "version":       s.version,
            "live_enabled":  s.live_enabled,
            "warmup_bars":   s.warmup_bars,
            "max_positions": s.max_positions,
        }
        for s in strats
    ]


@router.post("/strategies", status_code=201)
async def create_strategy(
    payload: CreateStrategyRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin only: add a strategy. It cannot be used live until enable-live."""
    from app.strategy.registry import get_strategy_class
    try:
        cls = get_strategy_class(payload.engine_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    s = Strategy(
        name           = payload.name,
        description    = payload.description,
        engine_class   = payload.engine_class,
        default_params = payload.default_params,
        is_available   = True,
        version        = cls.version,
        live_enabled   = False,
        warmup_bars    = cls.warmup_bars,
        max_positions  = cls.max_positions,
    )
    db.add(s)
    await db.commit()
    return {"id": str(s.id), "name": s.name, "version": s.version, "live_enabled": False}


@router.post("/strategies/{strategy_id}/enable-live")
async def enable_strategy_live(
    strategy_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.api.routes.strategies import enable_live_strategy
    return await enable_live_strategy(strategy_id, admin, db)


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


@router.post("/strategy-plugins/reload")
async def reload_strategy_plugins(admin: User = Depends(require_admin)):
    from app.strategy.registry import list_registered, refresh_plugins
    errors = refresh_plugins()
    return {"engines": list_registered(), "errors": errors}


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
    strat = await db.get(Strategy, payload.strategy_id)
    if not strat or not strat.is_available:
        raise HTTPException(status_code=404, detail="Strategy not found")
    from app.api.routes.strategies import _live_block
    reason = _live_block(strat, payload.paper_trading, payload.params, None, require_params=False)
    if reason:
        raise HTTPException(status_code=403, detail=reason)

    usm = UserStrategyMap(
        user_id           = payload.user_id,
        strategy_id       = payload.strategy_id,
        broker_account_id = payload.broker_account_id,
        params            = payload.params,
        engine_version    = strat.version,
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
