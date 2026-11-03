"""
Centralised Redis client.
Used for:
  - Market data Pub/Sub  (channel: "tick:{exchange}:{token}")
  - Strategy run-state   (key: "strategy:running:{user_strategy_map_id}")
  - Session tokens       (future)
"""
import redis.asyncio as aioredis
from app.core.config import settings

# One shared async connection pool for the whole app
_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _pool


def reset_redis() -> None:
    """Drop the cached client. The next get_redis() binds to the current loop."""
    global _pool
    _pool = None


async def close_redis() -> None:
    """Close the pooled client before its event loop is closed."""
    global _pool
    client = _pool
    _pool = None
    if client is None:
        return
    try:
        await client.aclose()
    except Exception:
        try:
            await client.close()
        except Exception:
            pass


# ── Pub/Sub channel helpers ───────────────────────────────────────────────────

def tick_channel(exchange: str, token: str) -> str:
    """Redis channel name for a single instrument's tick stream."""
    return f"tick:{exchange}:{token}"


def user_tick_channel(user_id: str) -> str:
    """Aggregated channel for all ticks relevant to a specific user."""
    return f"user_ticks:{user_id}"


# ── Strategy state keys ───────────────────────────────────────────────────────

def strategy_running_key(map_id: str) -> str:
    return f"strategy:running:{map_id}"


def strategy_state_key(map_id: str) -> str:
    """JSON blob of current strategy runtime state (position, params, etc.)"""
    return f"strategy:state:{map_id}"


def risk_state_key(map_id: str) -> str:
    """Persisted RiskManager counters (daily PnL, consecutive losses, kill)."""
    return f"risk:state:{map_id}"


# Global emergency stop for all live trading
LIVE_KILL_KEY = "trading:live_kill"

# Unix timestamp of the last real broker quote. Watchdog sets FEED_STALE_KEY.
FEED_HEARTBEAT_KEY = "feed:heartbeat"
FEED_STALE_KEY = "feed:stale"


def order_intent_key(client_order_id: str) -> str:
    """Claim key so one client_order_id can place at most one broker order."""
    return f"order:intent:{client_order_id}"
