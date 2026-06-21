"""
Options API routes — expiry list, option chain, per-user options watchlist.
"""
import logging, httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.core.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Underlying config
UNDERLYINGS = {
    "NIFTY50":    {"scrip": 13,  "seg": "IDX_I", "lot_size": 75},
    "BANKNIFTY":  {"scrip": 25,  "seg": "IDX_I", "lot_size": 30},
    "FINNIFTY":   {"scrip": 27,  "seg": "IDX_I", "lot_size": 40},
    "MIDCPNIFTY": {"scrip": 11,  "seg": "IDX_I", "lot_size": 75},
}

def _dhan_headers():
    return {
        "access-token": settings.DHAN_ACCESS_TOKEN,
        "client-id":    settings.DHAN_CLIENT_ID,
        "Content-Type": "application/json",
    }

# ── Expiry List ───────────────────────────────────────────────────────────────
@router.get("/expiry")
async def get_expiry_list(
    underlying: str = Query("NIFTY50"),
    current_user: User = Depends(get_current_user),
):
    """Fetch all expiry dates for a given underlying from Dhan."""
    cfg = UNDERLYINGS.get(underlying.upper())
    if not cfg:
        raise HTTPException(status_code=400, detail=f"Unknown underlying: {underlying}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.dhan.co/v2/optionchain/expirylist",
            headers=_dhan_headers(),
            json={"UnderlyingScrip": cfg["scrip"], "UnderlyingSeg": cfg["seg"]},
            timeout=10,
        )
    data = resp.json()
    if data.get("status") != "success":
        raise HTTPException(status_code=502, detail=str(data))

    from datetime import date, timedelta
    expiries = data.get("data", [])

    # Tag each expiry as weekly or monthly
    result = []
    for exp in expiries:
        d = date.fromisoformat(exp)
        # Monthly = last Thursday of the month
        # Weekly  = all other Thursdays
        # Simple check: if next expiry is within 8 days, it's weekly
        is_monthly = d.day > 24  # last week of month
        result.append({
            "date":    exp,
            "display": d.strftime("%d %b %Y"),
            "type":    "monthly" if is_monthly else "weekly",
            "days_to_expiry": (d - date.today()).days,
        })

    return {"underlying": underlying, "expiries": result, "lot_size": cfg["lot_size"]}

# ── Option Chain ──────────────────────────────────────────────────────────────
@router.get("/chain")
async def get_option_chain(
    underlying: str = Query("NIFTY50"),
    expiry:     str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Fetch full option chain with Greeks from Dhan."""
    cfg = UNDERLYINGS.get(underlying.upper())
    if not cfg:
        raise HTTPException(status_code=400, detail=f"Unknown underlying: {underlying}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.dhan.co/v2/optionchain",
            headers=_dhan_headers(),
            json={
                "UnderlyingScrip": cfg["scrip"],
                "UnderlyingSeg":   cfg["seg"],
                "Expiry":          expiry,
            },
            timeout=15,
        )
    data = resp.json()
    if data.get("status") != "success":
        raise HTTPException(status_code=502, detail=str(data))

    underlying_ltp = data["data"]["last_price"]
    oc             = data["data"]["oc"]

    # Build sorted strike list
    strikes = []
    for strike_str, sides in oc.items():
        strike = float(strike_str)
        ce     = sides.get("ce", {})
        pe     = sides.get("pe", {})
        strikes.append({
            "strike": strike,
            "ce": {
                "ltp":      ce.get("last_price"),
                "oi":       ce.get("oi"),
                "volume":   ce.get("volume"),
                "iv":       round(ce.get("implied_volatility", 0), 2),
                "delta":    ce.get("greeks", {}).get("delta"),
                "theta":    ce.get("greeks", {}).get("theta"),
                "gamma":    ce.get("greeks", {}).get("gamma"),
                "vega":     ce.get("greeks", {}).get("vega"),
                "bid":      ce.get("top_bid_price"),
                "ask":      ce.get("top_ask_price"),
                "security_id": str(ce.get("security_id", "")),
                "prev_oi":  ce.get("previous_oi"),
            } if ce else None,
            "pe": {
                "ltp":      pe.get("last_price"),
                "oi":       pe.get("oi"),
                "volume":   pe.get("volume"),
                "iv":       round(pe.get("implied_volatility", 0), 2),
                "delta":    pe.get("greeks", {}).get("delta"),
                "theta":    pe.get("greeks", {}).get("theta"),
                "gamma":    pe.get("greeks", {}).get("gamma"),
                "vega":     pe.get("greeks", {}).get("vega"),
                "bid":      pe.get("top_bid_price"),
                "ask":      pe.get("top_ask_price"),
                "security_id": str(pe.get("security_id", "")),
                "prev_oi":  pe.get("previous_oi"),
            } if pe else None,
        })

    strikes.sort(key=lambda x: x["strike"])

    # Find ATM strike
    atm = min(strikes, key=lambda x: abs(x["strike"] - underlying_ltp))

    return {
        "underlying":     underlying,
        "underlying_ltp": underlying_ltp,
        "expiry":         expiry,
        "lot_size":       cfg["lot_size"],
        "atm_strike":     atm["strike"],
        "strikes":        strikes,
    }

# ── Options Watchlist ─────────────────────────────────────────────────────────
@router.get("/watchlist")
async def get_options_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT * FROM user_options_watchlist WHERE user_id = :uid ORDER BY added_at DESC"),
        {"uid": str(current_user.id)}
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]

@router.post("/watchlist", status_code=201)
async def add_to_options_watchlist(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    try:
        await db.execute(
            text("""INSERT INTO user_options_watchlist
                (user_id, underlying, symbol, security_id, strike, option_type, expiry, exchange_segment, lot_size)
                VALUES (:uid, :underlying, :symbol, :security_id, :strike, :option_type, :expiry, :exchange_segment, :lot_size)
                ON CONFLICT (user_id, security_id) DO NOTHING"""),
            {
                "uid":              str(current_user.id),
                "underlying":       body.get("underlying", "NIFTY50"),
                "symbol":           body.get("symbol", ""),
                "security_id":      str(body.get("security_id", "")),
                "strike":           float(body.get("strike", 0)),
                "option_type":      body.get("option_type", "CE"),
                "expiry":           __import__("datetime").date.fromisoformat(str(body.get("expiry", "2099-01-01"))),
                "exchange_segment": body.get("exchange_segment", "NSE_FNO"),
                "lot_size":         int(body.get("lot_size", 75)),
            }
        )
        await db.commit()
        return {"status": "added"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/watchlist/{security_id}")
async def remove_from_options_watchlist(
    security_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    await db.execute(
        text("DELETE FROM user_options_watchlist WHERE user_id=:uid AND security_id=:sid"),
        {"uid": str(current_user.id), "sid": security_id}
    )
    await db.commit()
    return {"status": "removed"}

@router.get("/underlyings")
async def get_underlyings(current_user: User = Depends(get_current_user)):
    return [
        {"symbol": k, "lot_size": v["lot_size"], "scrip": v["scrip"]}
        for k, v in UNDERLYINGS.items()
    ]
