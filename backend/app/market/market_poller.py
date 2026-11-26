"""
Shared Market Poller
====================
Single background task that polls Dhan /marketfeed/ohlc once every 4 seconds
for ALL symbols. Results are broadcast to all connected WebSocket clients
via asyncio queues.

Architecture:
  One Dhan API call / 4s  →  fan out to N WebSocket clients
  
This ensures we never exceed Dhan's rate limit regardless of how many
browser tabs or users are connected.
"""
import asyncio
import logging
import httpx
from typing import Optional

from app.core.config import settings
from app.api.routes.market import DHAN_SECURITY_IDS
from app.market.daily_ohlc import (
    get_previous_day_ohlc,
    enqueue_daily_ohlc_fetch,
    start_daily_ohlc_worker,
)

logger = logging.getLogger(__name__)

# All 15 watchlist symbols — poll all of them in one request
ALL_SYMBOLS = list(DHAN_SECURITY_IDS.keys())

# Pre-build securities dict (never changes)
_SECURITIES: dict = {}
_SYM_INDEX:  dict = {}

for _sym in ALL_SYMBOLS:
    _inst = DHAN_SECURITY_IDS[_sym]
    _seg  = _inst["exchange_segment"]
    _sid  = _inst["security_id"]
    _SECURITIES.setdefault(_seg, []).append(int(_sid))
    _SYM_INDEX[(_seg, str(_sid))] = _sym


class MarketPoller:
    """
    Single shared Dhan poller. One API call per interval,
    results fanned out to all subscribed WebSocket clients.
    Supports dynamic add/remove of symbols.
    """

    def __init__(self, interval_seconds: Optional[float] = None):
        import os
        configured = float(getattr(settings, "MARKET_POLLER_INTERVAL_SECONDS", 1.0))
        self._interval   = float(interval_seconds if interval_seconds is not None else float(os.getenv("MARKET_POLLER_INTERVAL_SECONDS", configured)))
        self._queues:    list[asyncio.Queue] = []
        self._task:      Optional[asyncio.Task] = None
        self._last_data: list = []
        self._lock       = asyncio.Lock()
        self._ws_feed    = None
        self._loop:      Optional[asyncio.AbstractEventLoop] = None
        # Dynamic watchlist: symbol → {security_id, exchange_segment}
        self._watchlist: dict = {
            sym: {
                "security_id":      inst["security_id"],
                "exchange_segment": inst["exchange_segment"],
            }
            for sym, inst in DHAN_SECURITY_IDS.items()
        }

    @property
    def client_count(self) -> int:
        return len(self._queues)

    def set_interval(self, seconds: float):
        """Dynamically update polling frequency on the fly without restarting."""
        self._interval = max(0.5, float(seconds))
        logger.info(f"MarketPoller interval dynamically set to {self._interval}s")

    def add_symbol(self, symbol: str, security_id: str, exchange_segment: str):
        """Add a symbol to the watchlist."""
        if not symbol or not security_id:
            return
        sym_u = symbol.upper()
        existing = self._watchlist.get(sym_u)
        if (
            existing
            and str(existing.get("security_id")) == str(security_id)
            and existing.get("exchange_segment") == exchange_segment
        ):
            return

        self._watchlist[sym_u] = {
            "security_id":      str(security_id),
            "exchange_segment": exchange_segment,
        }
        enqueue_daily_ohlc_fetch(exchange_segment, str(security_id), sym_u)
        if self._ws_feed and self._ws_feed._running:
            self._ws_feed.subscribe(
                exchange=exchange_segment,
                security_id=str(security_id),
                token=str(security_id),
                symbol=sym_u,
            )
        logger.info(f"MarketPoller: added {symbol} ({exchange_segment}:{security_id})")

    def remove_symbol(self, symbol: str):
        """Remove a symbol from the watchlist."""
        sym_u = symbol.upper()
        self._watchlist.pop(sym_u, None)
        # Remove from cached data
        self._last_data = [t for t in self._last_data if t["symbol"] != sym_u]
        if self._ws_feed and self._ws_feed._running:
            self._ws_feed.unsubscribe(sym_u)
        logger.info(f"MarketPoller: removed {symbol}")

    def get_watchlist(self) -> list[str]:
        return list(self._watchlist.keys())

    def _build_securities(self) -> tuple[dict, dict]:
        """Build Dhan securities dict and index from current watchlist."""
        securities: dict = {}
        sym_index:  dict = {}
        for sym, info in self._watchlist.items():
            seg = info["exchange_segment"]
            sid = str(info["security_id"])
            securities.setdefault(seg, []).append(int(sid))
            sym_index[(seg, sid)] = sym
        return securities, sym_index

    async def _has_active_algos(self) -> bool:
        """Check if any active algo row is watching symbols."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.algo_row import BsaAlgoRow
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(BsaAlgoRow.id).where(BsaAlgoRow.is_algo_active == True).limit(1)
                )
                return res.scalar_one_or_none() is not None
        except Exception as e:
            logger.debug(f"Error checking active algos: {e}")
            return False

    def ensure_started(self):
        """Ensure the background poller loop and Dhan WebSocket live feed are running."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll_loop())
            logger.info("MarketPoller started autonomously")

        self._ensure_ws_feed_started()

    def _ensure_ws_feed_started(self):
        """Start the persistent Dhan WebSocket live feed in a daemon thread."""
        if not settings.DHAN_CLIENT_ID or not settings.DHAN_ACCESS_TOKEN:
            return
        if not getattr(settings, "DHAN_WS_FEED_ENABLED", True):
            return
        if self._ws_feed and self._ws_feed.is_connected:
            return

        try:
            from app.market.dhan_feed import DhanLiveFeed
            if not self._ws_feed:
                self._ws_feed = DhanLiveFeed(
                    client_id=settings.DHAN_CLIENT_ID,
                    access_token=settings.DHAN_ACCESS_TOKEN,
                    on_tick_callback=self._handle_live_ws_tick,
                )
            for sym, info in self._watchlist.items():
                self._ws_feed.subscribe(
                    exchange=info["exchange_segment"],
                    security_id=str(info["security_id"]),
                    token=str(info["security_id"]),
                    symbol=sym,
                )
            if not self._ws_feed._running:
                self._ws_feed.start()
                logger.info("MarketPoller: Dhan WebSocket live feed initialized and started")
        except Exception as e:
            logger.warning(f"Could not initialize Dhan WebSocket feed: {e}")

    def _handle_live_ws_tick(self, tick: dict):
        """Callback invoked on each incoming binary tick from Dhan WebSocket thread."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._process_ws_tick, tick)

    def _process_ws_tick(self, tick: dict):
        """Process a real-time WebSocket tick in the main event loop."""
        sym = tick.get("symbol")
        if not sym:
            return

        # 1. Update in-memory tick cache in place
        found = False
        for idx, existing in enumerate(self._last_data):
            if existing.get("symbol") == sym:
                self._last_data[idx] = {**existing, **tick}
                found = True
                break
        if not found:
            self._last_data.append(tick)

        # 2. Immediately dispatch to algo engine for millisecond trigger evaluation
        try:
            loop = self._loop
            if loop and loop.is_running():
                loop.create_task(self._notify_algo_engine([tick]))
            else:
                asyncio.create_task(self._notify_algo_engine([tick]))
        except RuntimeError:
            pass

        # 3. Broadcast to all active client WebSocket queues
        for q in list(self._queues):
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait([tick])
            except Exception:
                pass

    async def subscribe(self, symbols: str = "") -> asyncio.Queue:
        """Register a new WebSocket client. Returns a queue to receive ticks."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)

        async with self._lock:
            self._queues.append(q)

            # Send cached data immediately so client doesn't wait 4s
            if self._last_data:
                await q.put(self._last_data)

            # Start poller if this is the first subscriber
            if len(self._queues) == 1:
                self.ensure_started()

        return q

    async def unsubscribe(self, q: asyncio.Queue):
        """Remove a WebSocket client."""
        async with self._lock:
            if q in self._queues:
                self._queues.remove(q)

            # Stop poller only when no subscribers and no active algos remain
            if not self._queues and self._task:
                has_active = await self._has_active_algos()
                if not has_active:
                    self._task.cancel()
                    self._task = None
                    logger.info("MarketPoller stopped — no clients and no active algos")
                else:
                    logger.info("MarketPoller keeping background loop alive for active automated algo rows")

    async def _poll_loop(self):
        """Background task: poll Dhan and broadcast to all clients."""
        backoff = self._interval
        start_daily_ohlc_worker()

        # Enqueue initial watchlist symbols for daily OHLC loading
        for sym, info in self._watchlist.items():
            enqueue_daily_ohlc_fetch(info["exchange_segment"], str(info["security_id"]), sym)

        while True:
            try:
                securities, sym_index = self._build_securities()
                if not securities:
                    await asyncio.sleep(backoff)
                    continue

                # If live WebSocket feed is actively connected, skip redundant REST quote calls
                if self._ws_feed and self._ws_feed.is_connected:
                    await asyncio.sleep(self._interval)
                    continue

                # Fallback to shared rate-limited Dhan REST quotes
                from app.api.routes.market import _dhan_ohlc, _parse_ohlc
                raw_data = await asyncio.to_thread(
                    _dhan_ohlc,
                    securities,
                    settings.DHAN_CLIENT_ID,
                    settings.DHAN_ACCESS_TOKEN,
                )

                if raw_data:
                    ticks = []
                    for (seg, sid), sym in sym_index.items():
                        raw = raw_data.get(seg, {}).get(sid, {})
                        if not raw:
                            continue
                        tick = _parse_ohlc(raw, sym, segment=seg, security_id=sid)
                        ticks.append(tick)

                    if ticks:
                        self._last_data = ticks
                        backoff = max(1.5, self._interval)
                        try:
                            from app.core.redis_client import FEED_HEARTBEAT_KEY, get_redis
                            import time as _time
                            await get_redis().set(FEED_HEARTBEAT_KEY, str(_time.time()), ex=3600)
                        except Exception as exc:
                            logger.debug(f"Feed heartbeat write failed: {exc}")

                        # Dispatch to BSA Algo engine in background
                        asyncio.create_task(self._notify_algo_engine(ticks))

                        async with self._lock:
                            dead = []
                            for q in self._queues:
                                try:
                                    q.put_nowait(ticks)
                                except asyncio.QueueFull:
                                    pass
                                except Exception:
                                    dead.append(q)
                            for q in dead:
                                self._queues.remove(q)

                    logger.debug(f"MarketPoller: {len(ticks)} symbols → {len(self._queues)} clients")
                else:
                    backoff = min(backoff * 1.5, 10.0)

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"MarketPoller error: {e}")

            await asyncio.sleep(backoff)

    async def _notify_algo_engine(self, ticks: list[dict]):
        try:
            from app.core.database import AsyncSessionLocal
            from app.services.bsa_algo_engine import algo_engine
            async with AsyncSessionLocal() as db:
                for t in ticks:
                    sym = t.get("symbol")
                    if sym:
                        await algo_engine.evaluate_tick_for_symbol(sym, t, db)
        except Exception as e:
            logger.debug(f"Algo engine tick notification error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────

_poller: Optional[MarketPoller] = None


def get_poller() -> MarketPoller:
    """Get or create the singleton market poller."""
    global _poller
    if _poller is None:
        _poller = MarketPoller()
    return _poller
