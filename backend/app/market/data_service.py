"""
Market Data Service
===================
Manages a single Shoonya WebSocket connection and fans out
tick data to Redis Pub/Sub channels.

Architecture:
  Shoonya WS → on_tick() → Redis PUBLISH tick:{exchange}:{token}
                         → Redis PUBLISH user_ticks:{user_id}  (for subscribed users)

One instance runs per strategy worker process. Multiple strategies
on the same worker share the same WebSocket connection.
"""
import asyncio
import json
import logging
import threading
from typing import Callable

from app.core.redis_client import get_redis, tick_channel, user_tick_channel

logger = logging.getLogger(__name__)


class MarketDataService:
    """
    Wraps the Shoonya WebSocket feed.
    Call subscribe() to add instruments; the WS connection is
    started lazily on the first subscription.
    """

    def __init__(self, shoonya_adapter):
        self._adapter     = shoonya_adapter
        self._subscribed: set[str] = set()   # "EXCHANGE|TOKEN"
        self._started     = False
        self._lock        = threading.Lock()
        self._user_subs: dict[str, set[str]] = {}  # user_id → set of channels

    # ── Public API ────────────────────────────────────────────────────────────

    def subscribe(self, exchange: str, token: str, user_id: str | None = None):
        """
        Subscribe to tick feed for an instrument.
        exchange: "NSE" | "BSE" | "NFO" | "MCX"
        token:    Shoonya numeric instrument token (as string)
        user_id:  if given, ticks are also published to user_ticks:{user_id}
        """
        key = f"{exchange}|{token}"
        with self._lock:
            if key not in self._subscribed:
                self._subscribed.add(key)
                if self._started:
                    self._adapter.api.subscribe(key)
                    logger.info(f"Subscribed to {key}")

            if user_id:
                self._user_subs.setdefault(user_id, set()).add(tick_channel(exchange, token))

        if not self._started:
            self._start()

    def unsubscribe(self, exchange: str, token: str, user_id: str | None = None):
        key = f"{exchange}|{token}"
        with self._lock:
            self._subscribed.discard(key)
            if user_id:
                ch = tick_channel(exchange, token)
                self._user_subs.get(user_id, set()).discard(ch)
            if self._started:
                self._adapter.api.unsubscribe(key)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _start(self):
        """Launch Shoonya WebSocket in a background daemon thread."""
        with self._lock:
            if self._started:
                return
            self._started = True

        def _run():
            instruments = list(self._subscribed)
            logger.info(f"Starting Shoonya WS feed for {instruments}")
            self._adapter.subscribe_feed(
                instruments=instruments,
                on_tick=self._on_tick,
                on_order_update=self._on_order_update,
            )

        t = threading.Thread(target=_run, daemon=True, name="shoonya-ws")
        t.start()

    def _on_tick(self, tick: dict):
        """Called by Shoonya WS on every price update. Publish to Redis."""
        try:
            exchange = tick.get("e", "")
            token    = tick.get("tk", "")
            if not exchange or not token:
                return

            payload = json.dumps({
                "exchange": exchange,
                "token":    token,
                "ltp":      float(tick.get("lp", 0)),
                "volume":   int(tick.get("v", 0)),
                "open":     float(tick.get("o", 0)),
                "high":     float(tick.get("h", 0)),
                "low":      float(tick.get("l", 0)),
                "close":    float(tick.get("c", 0)),
                "ts":       tick.get("ft", ""),
            })

            redis = get_redis()
            channel = tick_channel(exchange, token)

            # Fire-and-forget publish (non-blocking)
            asyncio.run_coroutine_threadsafe(
                redis.publish(channel, payload),
                asyncio.get_event_loop(),
            )

            # Also publish to per-user channels
            for user_id, channels in self._user_subs.items():
                if channel in channels:
                    asyncio.run_coroutine_threadsafe(
                        redis.publish(user_tick_channel(user_id), payload),
                        asyncio.get_event_loop(),
                    )

        except Exception as e:
            logger.error(f"on_tick error: {e}")

    def _on_order_update(self, order: dict):
        logger.info(f"Order update from broker WS: {order}")


# ── Simulated tick publisher (for paper trading / dev without Shoonya creds) ──

class SimulatedMarketData:
    """
    Publishes synthetic OHLCV ticks to Redis at ~1 tick/sec.
    Used when paper_trading=True or Shoonya creds are absent.
    Generates realistic random-walk prices around a base price.
    """

    def __init__(self):
        self._running = False
        self._instruments: dict[str, float] = {}  # "EXCHANGE|TOKEN" → base_price

    def subscribe(self, exchange: str, token: str, base_price: float = 100.0, user_id: str | None = None):
        key = f"{exchange}|{token}"
        self._instruments[key] = base_price
        if not self._running:
            self._start()

    def _start(self):
        self._running = True
        t = threading.Thread(target=self._run_loop, daemon=True, name="sim-market")
        t.start()

    def _run_loop(self):
        import random, time
        import redis as sync_redis
        from app.core.config import settings

        # Use synchronous Redis client — no event loop needed in this thread
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)

        prices = dict(self._instruments)

        while self._running:
            for key, price in list(prices.items()):
                change = price * random.uniform(-0.001, 0.001)
                price  = round(price + change, 2)
                prices[key] = price

                parts    = key.split("|")
                exchange = parts[0] if len(parts) == 2 else "NSE"
                token    = parts[1] if len(parts) == 2 else key

                payload = json.dumps({
                    "exchange": exchange,
                    "token":    token,
                    "ltp":      price,
                    "volume":   random.randint(1000, 50000),
                    "open":     round(price * 0.999, 2),
                    "high":     round(price * 1.002, 2),
                    "low":      round(price * 0.998, 2),
                    "close":    round(price * 1.001, 2),
                    "ts":       str(int(time.time())),
                })

                try:
                    channel = tick_channel(exchange, token)
                    r.publish(channel, payload)
                except Exception as e:
                    logger.error(f"SimulatedMarketData publish error: {e}")

            time.sleep(1)
