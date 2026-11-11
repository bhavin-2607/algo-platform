"""
Dhan Live Market Feed Service
==============================
Connects to Dhan's WebSocket feed and publishes real NSE ticks
to Redis in the same format as SimulatedMarketData.

Uses the dhanhq SDK's marketfeed module which handles:
  - Binary packet parsing (LTP, OHLC, Volume, OI)
  - Ping/Pong keepalive
  - Auto-reconnect

Data flow:
  Dhan WebSocket → on_tick() → Redis Pub/Sub → Strategy Executor
  
Same Redis channel format as simulated feed:
  tick:{exchange}:{security_id}  e.g.  tick:NSE:26000

RequestCode reference:
  15 = Ticker (LTP only)
  17 = Quote  (LTP + OHLC + Volume)
  19 = Full   (Quote + Market Depth + OI)

We use Quote (17) for strategy evaluation — gives LTP, OHLC, Volume.
"""
import asyncio
import json
import logging
import threading
import time
import redis as sync_redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Dhan exchange segment → our internal exchange name
SEGMENT_MAP = {
    "NSE_EQ":   "NSE",
    "BSE_EQ":   "BSE",
    "NSE_FNO":  "NFO",
    "BSE_FNO":  "BFO",
    "MCX_COMM": "MCX",
    "IDX_I":    "IDX",
}

_CODE_TO_EXCHANGE = {
    0: "IDX",
    1: "NSE",
    2: "NFO",
    4: "BSE",
    5: "MCX",
    8: "BFO",
}


def redis_exchange(segment: str | None) -> str:
    """Name used on tick:{exchange}:{token}. Keeps cash and F&O on different channels."""
    seg = (segment or "NSE").upper()
    if seg in ("NSE_FNO", "NFO"):
        return "NFO"
    if seg in ("BSE_FNO", "BFO"):
        return "BFO"
    if seg in ("BSE_EQ", "BSE"):
        return "BSE"
    if seg in ("IDX_I", "IDX"):
        return "IDX"
    if seg in ("MCX", "MCX_COMM"):
        return "MCX"
    return "NSE"

# Common NSE instrument security IDs
# Full list: https://dhanhq.co/docs/v2/instruments/
COMMON_INSTRUMENTS = {
    "NIFTY50":    {"security_id": "13",    "exchange": "IDX_I",   "token": "13"},
    "BANKNIFTY":  {"security_id": "25",    "exchange": "IDX_I",   "token": "25"},
    "RELIANCE":   {"security_id": "2885",  "exchange": "NSE_EQ",  "token": "2885"},
    "TCS":        {"security_id": "11536", "exchange": "NSE_EQ",  "token": "11536"},
    "INFY":       {"security_id": "1594",  "exchange": "NSE_EQ",  "token": "1594"},
    "HDFCBANK":   {"security_id": "1333",  "exchange": "NSE_EQ",  "token": "1333"},
    "ICICIBANK":  {"security_id": "4963",  "exchange": "NSE_EQ",  "token": "4963"},
    "SBIN":       {"security_id": "3045",  "exchange": "NSE_EQ",  "token": "3045"},
    "WIPRO":      {"security_id": "3787",  "exchange": "NSE_EQ",  "token": "3787"},
    "TATAMOTORS": {"security_id": "3456",  "exchange": "NSE_EQ",  "token": "3456"},
    "BAJFINANCE": {"security_id": "317",   "exchange": "NSE_EQ",  "token": "317"},
}


class DhanLiveFeed:
    """
    Subscribes to Dhan WebSocket market feed and publishes ticks to Redis.
    Runs in a background thread — does not require an asyncio event loop.
    """

    def __init__(self, client_id: str, access_token: str):
        self._client_id    = client_id
        self._access_token = access_token
        self._redis        = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._running      = False
        self._thread: threading.Thread | None = None
        self._instruments: list = []   # Dhan format: (exchange_segment, security_id, mode)

    def subscribe(self, exchange: str, security_id: str, token: str | None = None):
        """
        Add an instrument to subscribe to.
        exchange: NSE / BSE / NFO etc.
        security_id: Dhan security ID (numeric string)
        token: our internal Redis channel token (defaults to security_id)
        """
        from dhanhq import marketfeed
        dhan_exchange = self._to_dhan_exchange(exchange)
        self._instruments.append({
            "dhan_exchange": dhan_exchange,
            "security_id":   str(security_id),
            "token":         token or str(security_id),
            "exchange":      exchange,
        })
        logger.info(f"Subscribed: {exchange}:{security_id} → tick:{exchange}:{token or security_id}")

    def subscribe_symbol(self, symbol: str):
        """Subscribe by common symbol name e.g. 'NIFTY50'."""
        info = COMMON_INSTRUMENTS.get(symbol.upper())
        if not info:
            logger.warning(f"Unknown symbol: {symbol} — use subscribe() with security_id directly")
            return
        self.subscribe(
            exchange    = redis_exchange(info["exchange"]),
            security_id = info["security_id"],
            token       = info["token"],
        )

    def start(self):
        """Start the feed in a background thread."""
        if self._running:
            logger.warning("DhanLiveFeed already running")
            return
        if not self._instruments:
            logger.error("No instruments subscribed — call subscribe() first")
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._run, daemon=True, name="dhan-live-feed"
        )
        self._thread.start()
        logger.info(f"DhanLiveFeed started with {len(self._instruments)} instruments")

    def stop(self):
        self._running = False
        logger.info("DhanLiveFeed stop requested")

    def _run(self):
        """Main feed loop — runs in background thread."""
        from dhanhq import marketfeed, DhanContext

        ctx = DhanContext(self._client_id, self._access_token)

        # Build instrument list in Dhan SDK format
        dhan_instruments = [
            (inst["dhan_exchange"], inst["security_id"], marketfeed.Quote)
            for inst in self._instruments
        ]

        # Build a lookup: (dhan_exchange, security_id) → our tick channel
        channel_map = {
            (inst["dhan_exchange"], inst["security_id"]): f"tick:{inst['exchange']}:{inst['token']}"
            for inst in self._instruments
        }

        retry_count = 0

        async def _listen():
            feed = marketfeed.MarketFeed(ctx, dhan_instruments, version="v2")
            await feed.connect()
            while self._running and feed.ws is not None:
                response = await feed.ws.recv()
                if not isinstance(response, (bytes, bytearray)):
                    continue
                data = feed.process_data(response)
                if isinstance(data, dict):
                    self._on_tick(data, channel_map)

        while self._running:
            try:
                logger.info("Connecting to Dhan live feed...")
                asyncio.run(_listen())
                retry_count = 0
            except Exception as e:
                if not self._running:
                    break
                retry_count += 1
                wait = min(retry_count * 5, 60)   # backoff up to 60s
                logger.error(f"Dhan feed error (retry {retry_count} in {wait}s): {e}")
                time.sleep(wait)

        logger.info("DhanLiveFeed stopped")

    def _on_tick(self, data: dict, channel_map: dict):
        """
        Called by dhanhq SDK on each tick.
        Parses the tick and publishes to Redis.

        Dhan Quote packet fields (from SDK):
          type, exchange_segment, security_id,
          LTP, LTQ, LTT, ATP, volume,
          total_sell_quantity, total_buy_quantity,
          open, close, high, low
        """
        if not data or not self._running:
            return

        try:
            exchange_segment = data.get("exchange_segment", "")
            security_id      = str(data.get("security_id", ""))
            ltp              = float(data.get("LTP") or 0)

            if ltp == 0:
                return

            # Find our Redis channel
            key     = (exchange_segment, security_id)
            channel = channel_map.get(key)
            if not channel:
                for (seg, sid), ch in channel_map.items():
                    if str(sid) == security_id:
                        channel = ch
                        break

            if not channel:
                logger.debug(f"No channel for {exchange_segment}:{security_id}")
                return

            if isinstance(exchange_segment, int):
                exchange = _CODE_TO_EXCHANGE.get(exchange_segment, "NSE")
            elif isinstance(exchange_segment, str):
                exchange = SEGMENT_MAP.get(
                    exchange_segment,
                    exchange_segment.split("_")[0] if "_" in exchange_segment else exchange_segment,
                )
            else:
                exchange = "NSE"

            payload = json.dumps({
                "exchange":  exchange,
                "token":     security_id,
                "ltp":       ltp,
                "volume":    int(float(data.get("volume") or 0)),
                "open":      float(data.get("open") or ltp),
                "high":      float(data.get("high") or ltp),
                "low":       float(data.get("low") or ltp),
                "close":     float(data.get("close") or ltp),
                "atp":       float(data.get("avg_price") or data.get("ATP") or ltp),
                "ltt":       0,
                "ltq":       int(float(data.get("LTQ") or 0)),
                "oi":        int(float(data.get("OI") or data.get("oi") or 0)),
                "ts":        str(int(time.time())),
                "source":    "dhan_live",
            })

            self._redis.publish(channel, payload)
            try:
                self._redis.set("feed:heartbeat", str(time.time()), ex=3600)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"DhanLiveFeed tick error: {e} | data={data}")

    @staticmethod
    def _to_dhan_exchange(exchange: str) -> int:
        """Dhan websocket exchange code. Unknown values stay on NSE cash."""
        mapping = {
            "NSE": 1,
            "NSE_EQ": 1,
            "NFO": 2,
            "NSE_FNO": 2,
            "NSE_CURRENCY": 3,
            "BSE": 4,
            "BSE_EQ": 4,
            "MCX": 5,
            "MCX_COMM": 5,
            "BSE_CURRENCY": 7,
            "BFO": 8,
            "BSE_FNO": 8,
            "IDX": 0,
            "IDX_I": 0,
        }
        return mapping.get((exchange or "NSE").upper(), 1)


# ── Singleton for use in Celery tasks ────────────────────────────────────────

_live_feed: DhanLiveFeed | None = None


def get_live_feed() -> DhanLiveFeed | None:
    return _live_feed


def start_dhan_feed(instruments: list[dict]) -> DhanLiveFeed:
    """
    Start the Dhan live feed with a list of instruments.
    instruments: [{"symbol": "NIFTY50"}, ...] or
                 [{"exchange": "NSE", "security_id": "26000", "token": "26000"}, ...]
    """
    global _live_feed

    if not settings.DHAN_CLIENT_ID or not settings.DHAN_ACCESS_TOKEN:
        raise ValueError("DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set in .env")

    feed = DhanLiveFeed(
        client_id    = settings.DHAN_CLIENT_ID,
        access_token = settings.DHAN_ACCESS_TOKEN,
    )

    for inst in instruments:
        if "symbol" in inst:
            feed.subscribe_symbol(inst["symbol"])
        elif "security_id" in inst:
            feed.subscribe(
                exchange    = inst.get("exchange", "NSE"),
                security_id = inst["security_id"],
                token       = inst.get("token", inst["security_id"]),
            )

    feed.start()
    _live_feed = feed
    return feed
