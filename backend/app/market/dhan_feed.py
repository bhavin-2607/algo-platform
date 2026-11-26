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
    "SENSEX":     {"security_id": "51",    "exchange": "IDX_I",   "token": "51"},
    "BANKEX":     {"security_id": "83",    "exchange": "IDX_I",   "token": "83"},
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


def _get_quote_code():
    try:
        from dhanhq import marketfeed
        mf = getattr(marketfeed, "MarketFeed", None)
        if mf and hasattr(mf, "Quote"):
            return mf.Quote
        if hasattr(marketfeed, "Quote"):
            return marketfeed.Quote
    except Exception:
        pass
    return 17


class DhanLiveFeed:
    """
    Subscribes to Dhan WebSocket market feed and publishes real-time ticks
    to both Redis and an in-memory async callback for MarketPoller & AlgoEngine.
    Runs in a background thread with automatic reconnect and dynamic subscriptions.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str,
        on_tick_callback=None,
    ):
        self._client_id    = client_id
        self._access_token = access_token
        self._on_tick_callback = on_tick_callback
        try:
            self._redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            self._redis = None
        self._running      = False
        self._is_connected = False
        self._last_tick_time = 0.0
        self._thread: threading.Thread | None = None
        self._market_feed_instance = None
        self._instruments: list = []   # Dhan format: (exchange_segment, security_id, mode)
        self._symbol_map: dict = {}    # (dhan_exchange, security_id) -> symbol
        self._channel_map: dict = {}   # (dhan_exchange, security_id) -> channel

    @property
    def is_alive(self) -> bool:
        """Returns True if the feed is connected and not stale."""
        if not (self._running and self._is_connected):
            return False
        if self._last_tick_time == 0.0:
            return True
        return (time.time() - self._last_tick_time < 60.0)

    @property
    def is_connected(self) -> bool:
        return self._running and self._is_connected

    def subscribe(self, exchange: str, security_id: str, token: str | None = None, symbol: str | None = None):
        """
        Add an instrument to subscribe to. Supports dynamic addition while feed is running.
        exchange: NSE / BSE / NFO etc.
        security_id: Dhan security ID (numeric string)
        token: our internal Redis channel token (defaults to security_id)
        symbol: optional human trading symbol e.g. 'NIFTY50'
        """
        from dhanhq import marketfeed
        dhan_exchange = self._to_dhan_exchange(exchange)
        sec_id_str = str(security_id).strip()

        # Check if already subscribed
        for item in self._instruments:
            if item["dhan_exchange"] == dhan_exchange and item["security_id"] == sec_id_str:
                if symbol:
                    self._symbol_map[(dhan_exchange, sec_id_str)] = symbol.upper()
                return

        inst = {
            "dhan_exchange": dhan_exchange,
            "security_id":   sec_id_str,
            "token":         token or sec_id_str,
            "exchange":      exchange,
            "symbol":        symbol.upper() if symbol else "",
        }
        self._instruments.append(inst)
        self._channel_map[(dhan_exchange, sec_id_str)] = f"tick:{exchange}:{token or sec_id_str}"
        if symbol:
            self._symbol_map[(dhan_exchange, sec_id_str)] = symbol.upper()

        logger.info(f"Subscribed: {exchange}:{sec_id_str} ({symbol or ''}) → tick:{exchange}:{token or sec_id_str}")

        # Thread-safe dynamic subscription: dispatch to background feed thread's event loop
        self._safe_dynamic_subscribe(dhan_exchange, sec_id_str)

    def _safe_dynamic_subscribe(self, dhan_exchange: int, sec_id_str: str):
        """Schedule dynamic subscription packet onto the background feed event loop."""
        if not self._market_feed_instance or not self._is_connected:
            return
        loop = getattr(self, "_feed_loop", None)
        if loop and loop.is_running():
            def _dispatch():
                try:
                    self._market_feed_instance.subscribe_symbols([(dhan_exchange, sec_id_str, _get_quote_code())])
                except Exception as e:
                    logger.debug(f"Dynamic subscribe_symbols error: {e}")
            try:
                loop.call_soon_threadsafe(_dispatch)
            except Exception as e:
                logger.debug(f"Failed to schedule dynamic subscription: {e}")

    def unsubscribe(self, symbol: str):
        """Unsubscribe by symbol name dynamically."""
        from dhanhq import marketfeed
        sym_u = (symbol or "").upper().strip()
        matched_keys = [k for k, s in self._symbol_map.items() if s == sym_u]
        if not matched_keys:
            return

        for k in matched_keys:
            dhan_ex, sec_id = k
            self._instruments = [i for i in self._instruments if not (i["dhan_exchange"] == dhan_ex and i["security_id"] == sec_id)]
            self._channel_map.pop(k, None)
            self._symbol_map.pop(k, None)
            if self._market_feed_instance and self._is_connected:
                try:
                    self._market_feed_instance.unsubscribe_symbols([(dhan_ex, sec_id, _get_quote_code())])
                except Exception as e:
                    logger.debug(f"Dynamic unsubscribe_symbols error: {e}")
        logger.info(f"Unsubscribed: {sym_u}")

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
            symbol      = symbol.upper(),
        )

    def start(self):
        """Start the feed in a background thread."""
        if self._running:
            logger.warning("DhanLiveFeed already running")
            return
        if not self._instruments:
            logger.warning("No instruments subscribed yet — feed will connect and await subscriptions")
        self._running = True
        self._thread  = threading.Thread(
            target=self._run, daemon=True, name="dhan-live-feed"
        )
        self._thread.start()
        logger.info(f"DhanLiveFeed started with {len(self._instruments)} instruments")

    def stop(self):
        self._running = False
        self._is_connected = False
        if self._market_feed_instance:
            try:
                self._market_feed_instance.close_connection()
            except Exception:
                pass
        logger.info("DhanLiveFeed stop requested")

    def _run(self):
        """Main feed loop — runs in background thread."""
        from dhanhq import marketfeed, DhanContext

        ctx = DhanContext(self._client_id, self._access_token)
        retry_count = 0

        async def _listen():
            self._feed_loop = asyncio.get_running_loop()
            # Build instrument list in Dhan SDK format
            dhan_instruments = [
                (inst["dhan_exchange"], inst["security_id"], _get_quote_code())
                for inst in self._instruments
            ]
            feed = marketfeed.MarketFeed(ctx, dhan_instruments, version="v2")
            self._market_feed_instance = feed
            await feed.connect()
            self._is_connected = True
            logger.info("DhanLiveFeed WebSocket connected successfully to api-feed.dhan.co")

            while self._running and feed.ws is not None:
                try:
                    response = await feed.ws.recv()
                except Exception as ex:
                    logger.warning(f"Dhan live feed connection recv exception: {ex}")
                    break

                if not isinstance(response, (bytes, bytearray)):
                    continue

                try:
                    data = feed.process_data(response)
                    if isinstance(data, dict):
                        self._on_tick(data, self._channel_map)
                except Exception as ex:
                    logger.debug(f"Dhan packet decode error: {ex}")

        while self._running:
            try:
                self._is_connected = False
                logger.info("Connecting to Dhan live feed WebSocket...")
                asyncio.run(_listen())
                retry_count = 0
            except Exception as e:
                self._is_connected = False
                if not self._running:
                    break
                retry_count += 1
                wait = min(retry_count * 3, 30)   # backoff up to 30s
                logger.error(f"Dhan feed WebSocket error (retry {retry_count} in {wait}s): {e}")
                time.sleep(wait)

        self._is_connected = False
        self._feed_loop = None
        logger.info("DhanLiveFeed stopped")

    def _on_tick(self, data: dict, channel_map: dict):
        """
        Called on each incoming binary tick packet.
        Parses tick, updates last tick time, invokes callback for MarketPoller,
        and optionally publishes to Redis.
        """
        if not data or not self._running:
            return

        try:
            exchange_segment = data.get("exchange_segment", "")
            security_id      = str(data.get("security_id", ""))
            ltp              = float(data.get("LTP") or 0)

            if ltp == 0:
                return

            self._last_tick_time = time.time()

            # Find matching symbol
            dhan_ex_code = exchange_segment if isinstance(exchange_segment, int) else self._to_dhan_exchange(str(exchange_segment))
            symbol = self._symbol_map.get((dhan_ex_code, security_id))
            if not symbol:
                for (ex_c, sid), sym in self._symbol_map.items():
                    if sid == security_id:
                        symbol = sym
                        break

            # Find our Redis channel
            key     = (exchange_segment, security_id)
            channel = channel_map.get(key)
            if not channel:
                for (seg, sid), ch in channel_map.items():
                    if str(sid) == security_id:
                        channel = ch
                        break

            if isinstance(exchange_segment, int):
                exchange = _CODE_TO_EXCHANGE.get(exchange_segment, "NSE")
                seg_str = self._to_segment_string(exchange_segment)
            elif isinstance(exchange_segment, str):
                exchange = SEGMENT_MAP.get(
                    exchange_segment,
                    exchange_segment.split("_")[0] if "_" in exchange_segment else exchange_segment,
                )
                seg_str = exchange_segment
            else:
                exchange = "NSE"
                seg_str = "NSE_EQ"

            open_val  = float(data.get("open") or ltp)
            high_val  = float(data.get("high") or ltp)
            low_val   = float(data.get("low") or ltp)
            close_val = float(data.get("close") or ltp)
            vol_val   = int(float(data.get("volume") or 0))
            avg_price = float(data.get("avg_price") or data.get("ATP") or ltp)
            oi_val    = int(float(data.get("OI") or data.get("oi") or 0))
            ltq_val   = int(float(data.get("LTQ") or 0))

            # Fetch previous day data from memory cache
            p_close = close_val
            p_high  = close_val
            p_low   = close_val
            p_open  = close_val
            try:
                from app.market.daily_ohlc import get_previous_day_ohlc
                p_data = get_previous_day_ohlc(seg_str, security_id)
                if p_data:
                    p_close = float(p_data.get("p_close") or close_val)
                    p_high  = float(p_data.get("p_high") or p_close)
                    p_low   = float(p_data.get("p_low") or p_close)
                    p_open  = float(p_data.get("p_open") or p_close)
            except Exception:
                pass

            change = round(ltp - p_close, 2)
            change_pct = round((change / max(p_close, 1)) * 100, 2)

            # Depth parsing
            depth = data.get("depth", [])
            bp1 = 0.0
            sp1 = 0.0
            buy_qty = 0
            sell_qty = 0
            if depth and isinstance(depth, list) and len(depth) > 0:
                first_d = depth[0]
                bp1 = float(first_d.get("bid_price") or 0.0)
                sp1 = float(first_d.get("ask_price") or 0.0)
                buy_qty = int(first_d.get("bid_quantity") or 0)
                sell_qty = int(first_d.get("ask_quantity") or 0)

            # In-process callback to MarketPoller / AlgoEngine
            if self._on_tick_callback and symbol:
                norm_tick = {
                    "symbol":     symbol,
                    "ltp":        ltp,
                    "open":       open_val,
                    "high":       high_val,
                    "low":        low_val,
                    "close":      close_val,
                    "p_close":    p_close,
                    "p_high":     p_high,
                    "p_low":      p_low,
                    "p_open":     p_open,
                    "change":     change,
                    "change_pct": change_pct,
                    "volume":     vol_val,
                    "oi":         oi_val,
                    "atp":        avg_price,
                    "vwap":       avg_price,
                    "buy_qty":    buy_qty,
                    "sell_qty":   sell_qty,
                    "bp1":        bp1,
                    "sp1":        sp1,
                    "net_change": change,
                    "source":     "dhan_ws",
                }
                try:
                    self._on_tick_callback(norm_tick)
                except Exception as exc:
                    logger.debug(f"Tick callback error for {symbol}: {exc}")

            # Publish to Redis channel if available
            if self._redis and channel:
                payload = json.dumps({
                    "exchange":  exchange,
                    "token":     security_id,
                    "ltp":       ltp,
                    "volume":    vol_val,
                    "open":      open_val,
                    "high":      high_val,
                    "low":       low_val,
                    "close":     close_val,
                    "atp":       avg_price,
                    "ltt":       0,
                    "ltq":       ltq_val,
                    "oi":        oi_val,
                    "ts":        str(int(time.time())),
                    "source":    "dhan_ws",
                })
                try:
                    self._redis.publish(channel, payload)
                    self._redis.set("feed:heartbeat", str(time.time()), ex=3600)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"DhanLiveFeed tick error: {e} | data={data}")

    @staticmethod
    def _to_segment_string(exchange_code: int) -> str:
        """Convert Dhan numeric exchange code to segment string."""
        mapping = {
            0: "IDX_I",
            1: "NSE_EQ",
            2: "NSE_FNO",
            3: "NSE_CURRENCY",
            4: "BSE_EQ",
            5: "MCX_COMM",
            7: "BSE_CURRENCY",
            8: "BSE_FNO",
        }
        return mapping.get(exchange_code, "NSE_EQ")

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
