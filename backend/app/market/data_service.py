"""
Simulated Market Data Service
=============================
Publishes synthetic OHLCV ticks to Redis at ~1 tick/sec for paper trading
and development testing without live broker market feeds.
"""
import logging
import threading
from app.core.redis_client import tick_channel, user_tick_channel

logger = logging.getLogger(__name__)


class SimulatedMarketData:
    """
    Publishes synthetic OHLCV ticks to Redis at ~1 tick/sec.
    Used when paper_trading=True.
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
            for key, base in list(self._instruments.items()):
                curr = prices.get(key, base)
                # ±0.15% random walk
                change = curr * random.uniform(-0.0015, 0.0015)
                new_price = round(curr + change, 2)
                prices[key] = new_price

                exchange, token = key.split("|")
                tick = {
                    "exchange":   exchange,
                    "token":      token,
                    "ltp":        new_price,
                    "open":       round(base * 0.998, 2),
                    "high":       round(max(base, new_price) * 1.002, 2),
                    "low":        round(min(base, new_price) * 0.997, 2),
                    "close":      round(base * 0.999, 2),
                    "p_close":    round(base * 0.995, 2),
                    "p_high":     round(base * 1.015, 2),
                    "p_low":      round(base * 0.985, 2),
                    "volume":     random.randint(100, 5000),
                    "timestamp":  int(time.time()),
                }

                import json
                payload = json.dumps(tick)
                try:
                    r.publish(tick_channel(exchange, token), payload)
                except Exception as e:
                    logger.warning(f"Sim tick publish error: {e}")

            time.sleep(1.0)
