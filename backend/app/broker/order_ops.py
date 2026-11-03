"""
Order helpers — fill confirmation, status normalization, and idempotent placement.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Optional

from app.broker.base import BaseBrokerAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)

# Covers a session restart that re-sees the same closed bar. Next bar gets a new id.
ORDER_INTENT_TTL_SEC = 18 * 3600


def client_order_id_for(map_id: str, bar_ts: Any, symbol: str, direction: str) -> str:
    """Stable id for one strategy map, closed bar, symbol, and side.

    Dhan correlationId allows up to 30 characters; 24 hex chars stays inside that.
    """
    ts = bar_ts.isoformat() if hasattr(bar_ts, "isoformat") else str(bar_ts)
    raw = f"{map_id}|{ts}|{symbol}|{direction}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


async def claim_order_intent(redis, client_order_id: str, ttl_sec: int = ORDER_INTENT_TTL_SEC) -> bool:
    """Return True only for the first caller. Later callers are duplicates."""
    from app.core.redis_client import order_intent_key

    ok = await redis.set(order_intent_key(client_order_id), "pending", nx=True, ex=ttl_sec)
    return bool(ok)


async def release_order_intent(redis, client_order_id: str) -> None:
    """Drop the claim when the broker never accepted the order, so a restart can retry."""
    from app.core.redis_client import order_intent_key

    await redis.delete(order_intent_key(client_order_id))


async def place_once(redis, adapter: BaseBrokerAdapter, order: OrderRequest, client_order_id: str) -> dict:
    """
    Claim client_order_id, place, and wait for a fill.

    Returns ok=True only when the broker reports FILLED.
    A second caller with the same id gets status DUPLICATE and does not place.
    """
    from app.core.trading_mode import LiveTradingError, assert_feed_fresh

    try:
        await assert_feed_fresh(redis)
    except LiveTradingError as exc:
        logger.error("place_once blocked: %s", exc.message)
        return {"ok": False, "status": "FEED_STALE", "fill_price": None, "broker_order_id": None}

    if not await claim_order_intent(redis, client_order_id):
        return {"ok": False, "status": "DUPLICATE", "fill_price": None, "broker_order_id": None}

    order.client_order_id = client_order_id
    try:
        resp = await adapter.place_order(order)
    except Exception as e:
        await release_order_intent(redis, client_order_id)
        logger.error(f"place_once error: {e}")
        return {"ok": False, "status": "FAILED", "fill_price": None, "broker_order_id": None}

    if not resp.broker_order_id or resp.status == "FAILED":
        await release_order_intent(redis, client_order_id)
        return {
            "ok": False,
            "status": "FAILED",
            "fill_price": None,
            "broker_order_id": None,
        }

    await commit_order_intent(redis, client_order_id, resp.broker_order_id)
    fill = await wait_for_fill(adapter, resp.broker_order_id)
    if fill["status"] != "FILLED":
        return {
            "ok": False,
            "status": fill["status"],
            "fill_price": None,
            "broker_order_id": resp.broker_order_id,
        }
    return {
        "ok": True,
        "status": "FILLED",
        "fill_price": fill["fill_price"],
        "broker_order_id": resp.broker_order_id,
    }


async def commit_order_intent(
    redis,
    client_order_id: str,
    broker_order_id: str,
    ttl_sec: int = ORDER_INTENT_TTL_SEC,
) -> None:
    """Keep the claim after the broker accepts the order and store its id."""
    from app.core.redis_client import order_intent_key

    await redis.set(order_intent_key(client_order_id), broker_order_id or "accepted", ex=ttl_sec)


_FILLED = {
    "COMPLETE", "COMPLETED", "FILLED", "TRADED", "FULLY_EXECUTED", "EXECUTED",
}
_REJECTED = {
    "REJECTED", "CANCELLED", "CANCELED", "EXPIRED", "FAILED", "REJECT",
}
_PENDING = {
    "OPEN", "PENDING", "TRANSIT", "TRIGGER_PENDING", "PENDING_NEW",
    "PARTIALLY_FILLED", "PARTIAL", "PENDING_CANCEL",
}


def normalize_order_status(raw_status: Any) -> str:
    """Map broker status strings → FILLED | REJECTED | PENDING | UNKNOWN."""
    if raw_status is None:
        return "UNKNOWN"
    s = str(raw_status).strip().upper().replace(" ", "_")
    if s in _FILLED:
        return "FILLED"
    if s in _REJECTED:
        return "REJECTED"
    if s in _PENDING:
        return "PENDING"
    # Dhan sometimes nests orderStatus
    return "UNKNOWN"


def _extract_status_and_price(raw: dict) -> tuple[str, Optional[float]]:
    if not raw:
        return "UNKNOWN", None

    status_raw = (
        raw.get("status")
        or raw.get("orderStatus")
        or raw.get("order_status")
        or ""
    )
    # Nested data blob from some Dhan responses
    if isinstance(raw.get("data"), dict):
        nested = raw["data"]
        status_raw = status_raw or nested.get("orderStatus") or nested.get("status") or ""
        price = (
            nested.get("averageTradedPrice")
            or nested.get("avgPrice")
            or nested.get("price")
            or nested.get("tradedPrice")
        )
    else:
        price = (
            raw.get("averageTradedPrice")
            or raw.get("avgPrice")
            or raw.get("price")
            or raw.get("tradedPrice")
        )

    fill_price = None
    try:
        if price is not None and float(price) > 0:
            fill_price = float(price)
    except (TypeError, ValueError):
        fill_price = None

    return normalize_order_status(status_raw), fill_price


async def wait_for_fill(
    adapter: BaseBrokerAdapter,
    broker_order_id: str,
    timeout_sec: Optional[float] = None,
    poll_interval: Optional[float] = None,
) -> dict:
    """
    Poll broker until order is FILLED, REJECTED, or timeout.

    Returns:
      {
        "status": "FILLED" | "REJECTED" | "TIMEOUT" | "UNKNOWN",
        "fill_price": float | None,
        "raw": dict,
      }
    """
    timeout_sec = timeout_sec if timeout_sec is not None else settings.ORDER_FILL_TIMEOUT_SEC
    poll_interval = (
        poll_interval if poll_interval is not None else settings.ORDER_FILL_POLL_INTERVAL_SEC
    )

    if not broker_order_id:
        return {"status": "REJECTED", "fill_price": None, "raw": {}}

    deadline = asyncio.get_event_loop().time() + float(timeout_sec)
    last_raw: dict = {}

    while True:
        try:
            last_raw = await adapter.get_order_status(broker_order_id) or {}
        except Exception as e:
            logger.warning(f"get_order_status error for {broker_order_id}: {e}")
            last_raw = {}

        status, fill_price = _extract_status_and_price(last_raw)
        if status == "FILLED":
            return {"status": "FILLED", "fill_price": fill_price, "raw": last_raw}
        if status == "REJECTED":
            return {"status": "REJECTED", "fill_price": None, "raw": last_raw}

        if asyncio.get_event_loop().time() >= deadline:
            logger.warning(
                f"Order fill timeout: id={broker_order_id} last_status={status}"
            )
            return {"status": "TIMEOUT", "fill_price": fill_price, "raw": last_raw}

        await asyncio.sleep(float(poll_interval))
