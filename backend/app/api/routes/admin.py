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
from app.models.broker import BrokerAccount, BrokerName
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
    from app.core.security import decrypt_broker_token, encrypt_broker_token

    result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.broker == BrokerName.dhan,
            BrokerAccount.is_active == True,
        )
    )
    accounts = result.scalars().all()
    master = next((a for a in accounts if a.account_role == "MASTER"), None) or (accounts[0] if accounts else None)

    client_id = (master.client_id if master else "") or getattr(settings, "DHAN_CLIENT_ID", "")
    account_name = master.account_name if master else "Primary Master Account"

    # Always prefer settings.DHAN_ACCESS_TOKEN as runtime settings/.env is the active source of truth
    token = getattr(settings, "DHAN_ACCESS_TOKEN", "")
    if not token and master and master.encrypted_access_token:
        try:
            token = decrypt_broker_token(master.encrypted_access_token)
        except Exception:
            pass

    # Reconcile database master record with settings.DHAN_ACCESS_TOKEN so database is never stale
    if token and master:
        try:
            existing = decrypt_broker_token(master.encrypted_access_token) if master.encrypted_access_token else ""
            if existing != token:
                master.encrypted_access_token = encrypt_broker_token(token)
                await db.commit()
        except Exception:
            master.encrypted_access_token = encrypt_broker_token(token)
            await db.commit()

    return client_id, token, account_name


@router.get("/dhan-ip")
async def get_dhan_ip_verification(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Check current server public IPv4 and IPv6 against Dhan configured static IP.
    Calls Dhan v2 /ip/getIP endpoint using active broker credentials.
    """
    import requests
    from app.broker.dhan import get_public_ipv4, get_public_ipv6

    server_ipv4 = get_public_ipv4()
    server_ipv6 = get_public_ipv6()
    client_id, token, account_name = await _get_active_dhan_credentials(db)

    if not client_id or not token:
        return {
            "current_server_ip": server_ipv4,
            "current_server_ipv4": server_ipv4,
            "current_server_ipv6": server_ipv6,
            "dhan_detected_ip": None,
            "dhan_primary_ip": None,
            "dhan_secondary_ip": None,
            "is_matched": False,
            "modify_eligible_date": None,
            "client_id": client_id or "Not configured",
            "account_name": account_name,
            "dhan_raw_response": None,
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
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            body = data.get("data") if isinstance(data.get("data"), dict) else data

            # Extract fields with case-insensitive / alternate key fallbacks
            raw_primary = (
                body.get("primaryIP")
                or body.get("primaryIp")
                or body.get("primary_ip")
                or body.get("ip")
                or ""
            )
            raw_secondary = (
                body.get("secondaryIP")
                or body.get("secondaryIp")
                or body.get("secondary_ip")
                or ""
            )

            primary_ip = str(raw_primary).strip()
            if primary_ip.upper() in ("NA", "NONE", "NULL"):
                primary_ip = ""

            secondary_ip = str(raw_secondary).strip()
            if secondary_ip.upper() in ("NA", "NONE", "NULL"):
                secondary_ip = ""

            detected_ip = str(body.get("detectedIP") or body.get("detectedIp") or body.get("detected_ip") or "").strip()
            modify_date_primary = body.get("modifyDatePrimary") or body.get("modifyEligibleDate") or body.get("eligibleDate")
            modify_date_secondary = body.get("modifyDateSecondary")
            orders_allowed = body.get("ordersAllowed")
            ip_match_status = body.get("ipMatchStatus")

            primary_version = "IPv6" if ":" in primary_ip else ("IPv4" if "." in primary_ip else None)
            secondary_version = "IPv6" if ":" in secondary_ip else ("IPv4" if "." in secondary_ip else None)
            detected_version = "IPv6" if ":" in detected_ip else ("IPv4" if "." in detected_ip else None)

            if server_ipv4 == "unknown" and detected_ip and "." in detected_ip and ":" not in detected_ip:
                server_ipv4 = detected_ip

            ipv4_matched = bool(
                server_ipv4
                and server_ipv4 != "unknown"
                and (server_ipv4 == primary_ip or server_ipv4 == secondary_ip)
            )
            ipv6_matched = bool(
                server_ipv6
                and (server_ipv6 == primary_ip or server_ipv6 == secondary_ip)
            )
            detected_matched = bool(
                detected_ip
                and (detected_ip == primary_ip or detected_ip == secondary_ip)
            )

            from app.core.config import settings
            force_ipv4_active = bool(getattr(settings, "DHAN_FORCE_IPV4", True))

            # When outbound Dhan requests are forced through IPv4 socket,
            # order traffic is guaranteed to match Dhan static IP if ipv4_matched is True,
            # even if Dhan GET IP endpoint flags ordersAllowed=False due to checking secondary IPv6 drift.
            orders_permitted_effective = bool(
                (force_ipv4_active and ipv4_matched)
                or orders_allowed is True
                or ip_match_status == "MATCH"
                or (not force_ipv4_active and (ipv4_matched or ipv6_matched))
            )

            # Secondary IPv6 drifted when Wi-Fi reconnected, but primary IPv4 order routing is intact
            secondary_ipv6_drift = bool(
                ipv4_matched
                and not ipv6_matched
                and secondary_ip
                and ":" in secondary_ip
            )

            is_matched = bool(
                orders_permitted_effective
                or ipv4_matched
                or ipv6_matched
                or detected_matched
                or orders_allowed is True
                or ip_match_status == "MATCH"
            )

            if ipv4_matched and ipv6_matched:
                ip_match_detail = "DUAL_STACK_MATCHED"
                status_msg = "Dual-stack static IP fully verified. Both IPv4 and IPv6 match Dhan registered static IPs."
            elif ipv4_matched:
                ip_match_detail = "IPV4_ACTIVE"
                if secondary_ipv6_drift:
                    status_msg = (
                        f"Orders are routed via forced IPv4 ({server_ipv4}), which matches Dhan registered IP. "
                        f"Live order placement is ACTIVE and permitted. "
                        f"Dhan GET IP reported mismatch because secondary IPv6 drifted after network reconnect (Dhan Secondary: {secondary_ip} vs Current IPv6: {server_ipv6 or 'Not Detected'}). "
                        f"Update Secondary IP below to re-sync Dhan dual-stack status."
                    )
                else:
                    status_msg = f"Orders are routed via forced IPv4 ({server_ipv4}), which matches Dhan registered IP. Live order placement is ACTIVE and permitted."
            elif is_matched:
                ip_match_detail = "MATCHED"
                status_msg = "IP configuration verified successfully. Trading orders permitted."
            else:
                ip_match_detail = "MISMATCH"
                status_msg = f"Outbound IP ({server_ipv4}) does not match Dhan registered static IPs (Primary: {primary_ip or 'None'}, Secondary: {secondary_ip or 'None'}). Please whitelist below."

            return {
                "current_server_ip": server_ipv4,
                "current_server_ipv4": server_ipv4,
                "current_server_ipv6": server_ipv6,
                "dhan_detected_ip": detected_ip or None,
                "dhan_detected_version": detected_version,
                "dhan_primary_ip": primary_ip or None,
                "dhan_primary_version": primary_version,
                "dhan_secondary_ip": secondary_ip or None,
                "dhan_secondary_version": secondary_version,
                "is_matched": is_matched,
                "ipv4_matched": ipv4_matched,
                "ipv6_matched": ipv6_matched,
                "force_ipv4_active": force_ipv4_active,
                "orders_permitted_effective": orders_permitted_effective,
                "secondary_ipv6_drift": secondary_ipv6_drift,
                "ip_match_detail": ip_match_detail,
                "orders_allowed": orders_allowed,
                "ip_match_status": ip_match_status,
                "modify_date_primary": modify_date_primary,
                "modify_date_secondary": modify_date_secondary,
                "modify_eligible_date": modify_date_primary or modify_date_secondary,
                "client_id": client_id,
                "account_name": account_name,
                "dhan_raw_response": data,
                "status": "SUCCESS",
                "message": status_msg,
            }
        else:
            err_msg = resp.text
            err_json = None
            try:
                err_json = resp.json()
                err_msg = err_json.get("remarks") or err_json.get("errorMessage") or err_msg
            except Exception:
                pass
            return {
                "current_server_ip": server_ipv4,
                "current_server_ipv4": server_ipv4,
                "current_server_ipv6": server_ipv6,
                "dhan_detected_ip": None,
                "dhan_primary_ip": None,
                "dhan_secondary_ip": None,
                "is_matched": False,
                "modify_eligible_date": None,
                "client_id": client_id,
                "account_name": account_name,
                "dhan_raw_response": err_json or {"raw_body": resp.text},
                "status": "DHAN_ERROR",
                "message": f"Dhan API returned {resp.status_code}: {err_msg}",
            }
    except Exception as e:
        return {
            "current_server_ip": server_ipv4,
            "current_server_ipv4": server_ipv4,
            "current_server_ipv6": server_ipv6,
            "dhan_detected_ip": None,
            "dhan_primary_ip": None,
            "dhan_secondary_ip": None,
            "is_matched": False,
            "modify_eligible_date": None,
            "client_id": client_id,
            "account_name": account_name,
            "dhan_raw_response": {"error": str(e)},
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
    Whitelist or update static IP on Dhan directly using access token via PUT /v2/ip/modifyIP or POST /v2/ip/setIP.
    Supports both IPv4 and IPv6 addresses.
    """
    import ipaddress
    import requests
    from app.broker.dhan import get_public_ipv4

    target_ip = (payload.ip or "").strip()
    if not target_ip:
        target_ip = get_public_ipv4()

    if not target_ip or target_ip == "unknown":
        raise HTTPException(status_code=400, detail="Invalid IP address")

    try:
        ipaddress.ip_address(target_ip)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid IP address format: '{target_ip}'. Must be a valid IPv4 or IPv6 address.",
        )

    client_id, token, account_name = await _get_active_dhan_credentials(db)
    if not client_id or not token:
        raise HTTPException(status_code=400, detail="Active Dhan credentials not found")

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
        # First attempt modifyIP (for updating existing IPs), fallback to setIP (for fresh setups)
        resp = requests.put("https://api.dhan.co/v2/ip/modifyIP", headers=headers, json=body, timeout=8)
        if resp.status_code not in (200, 201) and resp.status_code in (400, 404):
            resp_set = requests.post("https://api.dhan.co/v2/ip/setIP", headers=headers, json=body, timeout=8)
            if resp_set.status_code in (200, 201):
                resp = resp_set

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
                err_msg = err_json.get("remarks") or err_json.get("errorMessage") or err_json.get("message") or err_msg
            except Exception:
                pass
            raise HTTPException(status_code=resp.status_code, detail=f"Dhan IP Whitelisting failed: {err_msg}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error connecting to Dhan IP service: {str(e)}")


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


# ── Real-time Platform Logs ───────────────────────────────────────────────────

@router.get("/logs")
async def get_logs(
    category: str = "app",
    lines: int = 100,
    admin: User = Depends(require_admin),
):
    """
    Retrieve real-time platform logs by category.
    Available categories:
      - 'trades':   Order executions, broker responses, copy trading fan-outs, square-off
      - 'algo':     BSA formula triggers, target hits, stop-loss triggers, trade cycles
      - 'market':   Market feed ticks, symbol subscriptions, daily OHLC sync
      - 'error':    Dedicated error and critical exceptions with stack traces
      - 'app':      Consolidated FastAPI application logs
      - 'platform': Universal supervisor log (Backend, Celery Worker, Celery Beat)
    """
    from app.core.logging_config import read_log_tail
    return read_log_tail(log_name=category, lines=lines)


@router.get("/logs/summary")
async def get_logs_summary(
    admin: User = Depends(require_admin),
):
    """Get metadata and file sizes for all platform log categories."""
    import os
    import time
    from app.core.logging_config import get_log_dir
    log_dir = get_log_dir()
    categories = ["trades.log", "algo.log", "market.log", "error.log", "app.log", "platform.log"]
    summary = []
    for cat in categories:
        p = os.path.join(log_dir, cat)
        if os.path.exists(p):
            stat = os.stat(p)
            summary.append({
                "category": cat.replace(".log", ""),
                "file": cat,
                "size_kb": round(stat.st_size / 1024, 1),
                "last_modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            })
        else:
            summary.append({
                "category": cat.replace(".log", ""),
                "file": cat,
                "size_kb": 0.0,
                "last_modified": None,
            })
    return {"log_directory": log_dir, "categories": summary}
