"""
Copy Trading Routes
===================

POST /api/signals/webhook/{leader_token}
  - TradingView fires this URL with a JSON alert payload
  - No user auth needed — secured by the leader_token in the URL
  - Immediately fans out to all followers

GET/POST /api/signals/copy-relationships
  - Manage who follows whom

GET /api/signals/feed (WebSocket)
  - Followers subscribe here to get real-time signal notifications
"""
import hashlib
import hmac
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.signal import Signal, SignalDirection, SignalStatus, CopyRelationship
from app.models.broker import BrokerAccount
from app.services.fanout import fanout_signal

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Webhook endpoint (called by TradingView) ─────────────────────────────────

@router.post("/webhook/{webhook_token}")
async def tradingview_webhook(
    webhook_token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    TradingView fires this endpoint when a Pine Script alert triggers.

    Expected JSON payload from Pine Script alert message:
    {
      "token":     "{{strategy.order.comment}}",  ← your webhook_token
      "symbol":    "{{ticker}}",
      "exchange":  "NSE",
      "direction": "{{strategy.order.action}}",   ← "buy" or "sell"
      "quantity":  {{strategy.order.contracts}},
      "price":     {{close}},
      "tag":       "MA_CROSS"
    }
    """
    # Parse body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    logger.info(f"Webhook received: {body}")

    # Find leader by webhook token
    result = await db.execute(
        select(User).where(User.webhook_token == webhook_token)
    )
    leader = result.scalar_one_or_none()
    if not leader:
        raise HTTPException(status_code=404, detail="Invalid webhook token")

    # Parse direction
    raw_dir = str(body.get("direction", "")).upper()
    if raw_dir in ("BUY", "LONG", "B"):
        direction = SignalDirection.BUY
    elif raw_dir in ("SELL", "SHORT", "S"):
        direction = SignalDirection.SELL
    elif raw_dir in ("EXIT", "CLOSE"):
        direction = SignalDirection.EXIT
    else:
        raise HTTPException(status_code=400, detail=f"Unknown direction: {raw_dir}")

    symbol   = str(body.get("symbol", "")).upper().replace(".NS", "").replace("NSE:", "")
    exchange = str(body.get("exchange", "NSE")).upper()
    qty_raw  = body.get("quantity")
    quantity = int(qty_raw) if qty_raw else None
    price    = float(body.get("price", 0)) or None

    # Create signal record
    signal = Signal(
        leader_id    = leader.id,
        symbol       = symbol,
        exchange     = exchange,
        direction    = direction,
        quantity     = quantity,
        price        = price,
        strategy_tag = body.get("tag", "TV_ALERT"),
        raw_payload  = body,
        status       = SignalStatus.received,
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)

    # Fan out in background so webhook returns immediately
    background_tasks.add_task(fanout_signal, signal, db)

    return {
        "status":    "received",
        "signal_id": str(signal.id),
        "symbol":    symbol,
        "direction": direction,
    }


# ── Leader: get webhook URL ───────────────────────────────────────────────────

@router.get("/my-webhook")
async def get_my_webhook(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the webhook URL the leader should paste into TradingView."""
    if not current_user.webhook_token:
        # Generate and save a token
        import secrets
        current_user.webhook_token = secrets.token_urlsafe(32)
        await db.commit()

    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/signals/webhook/{current_user.webhook_token}"

    return {
        "webhook_url":   webhook_url,
        "webhook_token": current_user.webhook_token,
        "instructions":  _pine_script_example(current_user.webhook_token),
    }


# ── Copy relationships ────────────────────────────────────────────────────────

class FollowRequest(BaseModel):
    leader_id:         UUID
    broker_account_id: Optional[UUID] = None
    auto_execute:      bool  = True
    qty_multiplier:    float = 1.0


@router.post("/follow", status_code=201)
async def follow_leader(
    payload: FollowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start copying a leader's trades."""
    if payload.leader_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    # Check leader exists
    leader = await db.get(User, payload.leader_id)
    if not leader:
        raise HTTPException(status_code=404, detail="Leader not found")

    # Prevent duplicates
    existing = await db.execute(
        select(CopyRelationship).where(
            CopyRelationship.leader_id   == payload.leader_id,
            CopyRelationship.follower_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already following this leader")

    rel = CopyRelationship(
        leader_id         = payload.leader_id,
        follower_id       = current_user.id,
        broker_account_id = payload.broker_account_id,
        auto_execute      = payload.auto_execute,
        qty_multiplier    = payload.qty_multiplier,
        is_active         = True,
    )
    db.add(rel)
    await db.commit()
    return {"status": "following", "leader": leader.username}


@router.get("/following")
async def list_following(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all leaders the current user is copying."""
    result = await db.execute(
        select(CopyRelationship)
        .where(CopyRelationship.follower_id == current_user.id)
    )
    rels = result.scalars().all()
    out = []
    for r in rels:
        leader = await db.get(User, r.leader_id)
        out.append({
            "id":              str(r.id),
            "leader_id":       str(r.leader_id),
            "leader_username": leader.username if leader else "unknown",
            "auto_execute":    r.auto_execute,
            "qty_multiplier":  r.qty_multiplier,
            "is_active":       r.is_active,
        })
    return out


@router.patch("/following/{rel_id}")
async def update_follow(
    rel_id: UUID,
    auto_execute: Optional[bool] = None,
    qty_multiplier: Optional[float] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause/resume or adjust a copy relationship."""
    result = await db.execute(
        select(CopyRelationship).where(
            CopyRelationship.id          == rel_id,
            CopyRelationship.follower_id == current_user.id,
        )
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    if auto_execute  is not None: rel.auto_execute   = auto_execute
    if qty_multiplier is not None: rel.qty_multiplier = qty_multiplier
    if is_active     is not None: rel.is_active       = is_active
    await db.commit()
    return {"status": "updated"}


@router.delete("/following/{rel_id}", status_code=204)
async def unfollow(
    rel_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop copying a leader."""
    result = await db.execute(
        select(CopyRelationship).where(
            CopyRelationship.id          == rel_id,
            CopyRelationship.follower_id == current_user.id,
        )
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")
    await db.delete(rel)
    await db.commit()


@router.get("/followers")
async def list_followers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Leader sees who is copying them."""
    result = await db.execute(
        select(CopyRelationship)
        .where(CopyRelationship.leader_id == current_user.id)
    )
    rels = result.scalars().all()
    out = []
    for r in rels:
        follower = await db.get(User, r.follower_id)
        out.append({
            "id":               str(r.id),
            "follower_id":      str(r.follower_id),
            "follower_username":follower.username if follower else "unknown",
            "auto_execute":     r.auto_execute,
            "qty_multiplier":   r.qty_multiplier,
            "is_active":        r.is_active,
        })
    return out


@router.get("/history")
async def signal_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """History of signals sent (for leaders) or received (for followers)."""
    result = await db.execute(
        select(Signal)
        .where(Signal.leader_id == current_user.id)
        .order_by(Signal.created_at.desc())
        .limit(limit)
    )
    signals = result.scalars().all()
    return [
        {
            "id":           str(s.id),
            "symbol":       s.symbol,
            "exchange":     s.exchange,
            "direction":    s.direction,
            "quantity":     s.quantity,
            "price":        s.price,
            "strategy_tag": s.strategy_tag,
            "status":       s.status,
            "created_at":   s.created_at.isoformat(),
        }
        for s in signals
    ]


# ── Pine Script example ───────────────────────────────────────────────────────

def _pine_script_example(token: str) -> str:
    return f"""
// Paste this into your TradingView Alert → Message field:
{{
  "token":     "{token}",
  "symbol":    "{{{{ticker}}}}",
  "exchange":  "NSE",
  "direction": "{{{{strategy.order.action}}}}",
  "quantity":  {{{{strategy.order.contracts}}}},
  "price":     {{{{close}}}},
  "tag":       "MY_STRATEGY"
}}

// In Alert Settings:
//   Webhook URL: your-server-url/api/signals/webhook/{token}
//   Message:     paste above JSON
"""


# ── Manual signal (fallback for no TradingView) ───────────────────────────────

class ManualSignalRequest(BaseModel):
    symbol:       str
    exchange:     str  = "NSE"
    direction:    str  # BUY / SELL / EXIT
    quantity:     Optional[int]   = None
    price:        Optional[float] = None
    strategy_tag: str = "MANUAL"


@router.post("/manual", status_code=201)
async def post_manual_signal(
    payload: ManualSignalRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Leader posts a signal manually from the UI.
    Fans out to all followers exactly like a TradingView webhook.
    """
    raw_dir = payload.direction.upper()
    if raw_dir in ("BUY", "LONG"):
        direction = SignalDirection.BUY
    elif raw_dir in ("SELL", "SHORT"):
        direction = SignalDirection.SELL
    elif raw_dir in ("EXIT", "CLOSE"):
        direction = SignalDirection.EXIT
    else:
        raise HTTPException(status_code=400, detail=f"Unknown direction: {raw_dir}")

    signal = Signal(
        leader_id    = current_user.id,
        symbol       = payload.symbol.upper(),
        exchange     = payload.exchange.upper(),
        direction    = direction,
        quantity     = payload.quantity,
        price        = payload.price,
        strategy_tag = payload.strategy_tag,
        raw_payload  = payload.model_dump(),
        status       = SignalStatus.received,
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)

    background_tasks.add_task(fanout_signal, signal, db)

    return {
        "status":    "sent",
        "signal_id": str(signal.id),
        "symbol":    signal.symbol,
        "direction": direction,
        "followers": "fanning out...",
    }
