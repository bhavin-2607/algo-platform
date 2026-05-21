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

    def __init__(self, interval_seconds: float = 4.0):
        self._interval   = interval_seconds
        self._queues:    list[asyncio.Queue] = []
        self._task:      Optional[asyncio.Task] = None
        self._last_data: list = []
        self._lock       = asyncio.Lock()
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

    def add_symbol(self, symbol: str, security_id: str, exchange_segment: str):
        """Add a symbol to the watchlist."""
        self._watchlist[symbol.upper()] = {
            "security_id":      str(security_id),
            "exchange_segment": exchange_segment,
        }
        logger.info(f"MarketPoller: added {symbol} ({exchange_segment}:{security_id})")

    def remove_symbol(self, symbol: str):
        """Remove a symbol from the watchlist."""
        self._watchlist.pop(symbol.upper(), None)
        # Remove from cached data
        self._last_data = [t for t in self._last_data if t["symbol"] != symbol.upper()]
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

    @property
    def client_count(self) -> int:
        return len(self._queues)

    async def subscribe(self, symbols: str = "") -> asyncio.Queue:
        """Register a new WebSocket client. Returns a queue to receive ticks."""
        q: asyncio.Queue = asyncio.Queue(maxsize=10)

        async with self._lock:
            self._queues.append(q)

            # Send cached data immediately so client doesn't wait 4s
            if self._last_data:
                await q.put(self._last_data)

            # Start poller if this is the first subscriber
            if len(self._queues) == 1:
                self._task = asyncio.create_task(self._poll_loop())
                logger.info("MarketPoller started")

        return q

    async def unsubscribe(self, q: asyncio.Queue):
        """Remove a WebSocket client."""
        async with self._lock:
            if q in self._queues:
                self._queues.remove(q)

            # Stop poller when no subscribers left
            if not self._queues and self._task:
                self._task.cancel()
                self._task = None
                logger.info("MarketPoller stopped — no clients")

    async def _poll_loop(self):
        """Background task: poll Dhan and broadcast to all clients."""
        headers = {
            "access-token": settings.DHAN_ACCESS_TOKEN,
            "client-id":    settings.DHAN_CLIENT_ID,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        }
        backoff = self._interval

        async with httpx.AsyncClient(timeout=4) as client:
            while True:
                try:
                    securities, sym_index = self._build_securities()
                    if not securities:
                        await asyncio.sleep(backoff)
                        continue

                    resp = await client.post(
                        "https://api.dhan.co/v2/marketfeed/ohlc",
                        headers=headers,
                        json=securities,
                    )
                    data = resp.json()

                    if data.get("status") == "success":
                        ticks    = []
                        raw_data = data.get("data", {})

                        for (seg, sid), sym in sym_index.items():
                            raw = raw_data.get(seg, {}).get(sid, {})
                            if not raw:
                                continue
                            ltp   = float(raw.get("last_price", 0))
                            ohlc  = raw.get("ohlc", {})
                            close = float(ohlc.get("close", ltp))
                            ticks.append({
                                "symbol":     sym,
                                "ltp":        ltp,
                                "open":       float(ohlc.get("open",  ltp)),
                                "high":       float(ohlc.get("high",  ltp)),
                                "low":        float(ohlc.get("low",   ltp)),
                                "close":      close,
                                "change":     round(ltp - close, 2),
                                "change_pct": round((ltp - close) / max(close, 1) * 100, 2),
                                "source":     "dhan_live",
                            })

                        if ticks:
                            self._last_data = ticks
                            backoff = self._interval

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

                    elif "805" in str(data):
                        backoff = min(backoff * 2, 30)
                        logger.warning(f"Dhan rate limit — backing off to {backoff:.0f}s")
                    else:
                        logger.warning(f"Dhan OHLC error: {data}")

                except httpx.TimeoutException:
                    logger.warning("MarketPoller: timeout")
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    logger.error(f"MarketPoller error: {e}")

                await asyncio.sleep(backoff)


# ── Singleton ─────────────────────────────────────────────────────────────────

_poller: Optional[MarketPoller] = None


def get_poller() -> MarketPoller:
    """Get or create the singleton market poller."""
    global _poller
    if _poller is None:
        _poller = MarketPoller(interval_seconds=4.0)
    return _poller
