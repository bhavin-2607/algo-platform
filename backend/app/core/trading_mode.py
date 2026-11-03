"""
Paper vs live trading gates.

Live capital paths must call assert_live_allowed() / require_not_killed()
before placing real broker orders or starting live feeds.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.redis_client import get_redis, LIVE_KILL_KEY

logger = logging.getLogger(__name__)


class LiveTradingError(Exception):
    """Raised when live trading is blocked by config or kill switch."""

    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def assert_live_allowed() -> None:
    """Raise LiveTradingError unless live trading is explicitly enabled and Dhan is configured."""
    if not settings.LIVE_TRADING_ENABLED:
        raise LiveTradingError(
            "Live trading is disabled. Set LIVE_TRADING_ENABLED=true in .env to allow real orders."
        )
    if not settings.DHAN_CLIENT_ID or not settings.DHAN_ACCESS_TOKEN:
        raise LiveTradingError(
            "Live trading requires DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in .env.",
            status_code=400,
        )


async def is_live_killed() -> bool:
    redis = get_redis()
    return bool(await redis.get(LIVE_KILL_KEY))


async def get_live_kill_info() -> dict | None:
    redis = get_redis()
    raw = await redis.get(LIVE_KILL_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"reason": str(raw)}


async def set_live_kill(reason: str = "manual") -> dict:
    """Activate global live kill — blocks new live starts/orders and clears running flags."""
    redis = get_redis()
    payload = {
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.set(LIVE_KILL_KEY, json.dumps(payload))

    # Stop all running strategy executors
    stopped = 0
    async for key in redis.scan_iter(match="strategy:running:*"):
        await redis.delete(key)
        stopped += 1

    logger.error(f"LIVE KILL activated: {reason} (stopped {stopped} running keys)")
    return {**payload, "stopped_running_keys": stopped}


async def clear_live_kill() -> None:
    redis = get_redis()
    await redis.delete(LIVE_KILL_KEY)
    logger.warning("LIVE KILL cleared — live starts/orders allowed again (if LIVE_TRADING_ENABLED)")


async def require_not_killed() -> None:
    info = await get_live_kill_info()
    if info:
        reason = info.get("reason", "unknown")
        raise LiveTradingError(
            f"Global live kill switch is active ({reason}). Clear it before live trading."
        )
