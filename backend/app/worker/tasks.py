"""
Celery Tasks — strategy execution pipeline.
Each task creates its own fresh event loop + DB session to avoid
"event loop is closed" and "another operation in progress" errors.
"""
import logging
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro_factory):
    """
    Run an async coroutine factory with a fresh event loop each time.
    Pass a zero-arg async function (lambda/def), NOT an already-created coroutine,
    so the coroutine is created INSIDE the new loop.

    The shared Redis client and DB engine are closed with that loop. The next
    task creates new ones. Reusing them across loops raises "Event loop is closed".
    """
    import asyncio
    from app.core.redis_client import close_redis, reset_redis

    async def _shutdown():
        await close_redis()
        try:
            from app.core.database import engine
            await engine.dispose()
        except Exception:
            pass

    reset_redis()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        try:
            loop.run_until_complete(_shutdown())
        except Exception:
            reset_redis()
        try:
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(None)


# ── Strategy executor ─────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, name="tasks.run_strategy")
def run_strategy(self, user_strategy_map_id: str):
    """Full loop: tick → candle → signal → risk → order → DB log."""

    async def _execute():
        from app.core.database import AsyncSessionLocal
        from app.strategy.executor import StrategyExecutor
        async with AsyncSessionLocal() as db:
            executor = StrategyExecutor(map_id=user_strategy_map_id, db=db)
            try:
                await executor.start()
            except Exception as exc:
                logger.error(f"Executor error [{user_strategy_map_id}]: {exc}")
                raise self.retry(exc=exc, countdown=10)

    _run(_execute)


# ── Simulated market feed ─────────────────────────────────────────────────────

@celery_app.task(name="tasks.start_dhan_feed")
def start_dhan_feed(instruments: list):
    """
    Start Dhan live market feed — publishes real NSE ticks to Redis.
    instruments: [{"symbol": "NIFTY50"}, ...] or
                 [{"exchange": "NSE", "security_id": "26000", "token": "26000"}, ...]
    Runs indefinitely until process is killed.
    """
    from app.market.dhan_feed import start_dhan_feed as _start_feed
    import time

    logger.info(f"Starting Dhan live feed for {len(instruments)} instruments")
    feed = _start_feed(instruments)

    # Keep task alive while feed is running
    while feed._running:
        time.sleep(5)


@celery_app.task(name="tasks.start_simulated_feed")
def start_simulated_feed(exchange: str, token: str, base_price: float = 2800.0):
    """Publish synthetic ticks to Redis every second (paper trading / dev)."""
    import time
    from app.core.trading_mode import LiveTradingError, assert_synthetic_allowed

    try:
        assert_synthetic_allowed()
    except LiveTradingError as exc:
        logger.error(str(exc))
        return

    from app.market.data_service import SimulatedMarketData
    sim = SimulatedMarketData()
    sim.subscribe(exchange=exchange, token=token, base_price=base_price)
    while True:
        time.sleep(60)


# ── Stop strategy ─────────────────────────────────────────────────────────────

@celery_app.task(name="tasks.stop_strategy")
def stop_strategy(user_strategy_map_id: str):
    """Delete the running key so the executor loop exits cleanly."""

    async def _stop():
        from app.core.database import AsyncSessionLocal
        from app.core.redis_client import get_redis, strategy_running_key
        from app.strategy.recovery import flatten_map
        redis = get_redis()
        await redis.delete(strategy_running_key(user_strategy_map_id))
        async with AsyncSessionLocal() as db:
            await flatten_map(db, redis, user_strategy_map_id, reason="STOP")

    _run(_stop)


# ── Daily risk reset ──────────────────────────────────────────────────────────

@celery_app.task(name="tasks.reset_daily_risk")
def reset_daily_risk():
    """Called at 9:15 AM IST via Celery Beat — clears daily P&L counters."""

    async def _reset():
        import json
        from app.core.redis_client import get_redis
        redis = get_redis()
        keys = await redis.keys("strategy:state:*")
        keys += await redis.keys("risk:state:*")
        for key in keys:
            raw = await redis.get(key)
            if raw:
                try:
                    state = json.loads(raw)
                    state.update({"daily_pnl": 0.0, "consecutive_losses": 0, "killed": False})
                    await redis.set(key, json.dumps(state), ex=86400)
                except Exception:
                    pass
        logger.info(f"Daily risk reset for {len(keys)} strategies")
        from app.core.audit import write_audit
        await write_audit("daily_risk_reset", f"Reset {len(keys)} risk state keys")

    _run(_reset)


@celery_app.task(name="tasks.feed_watchdog")
def feed_watchdog():
    """During the cash session, pause new live orders when quotes stop arriving."""

    async def _check():
        import time
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from app.core.alerts import raise_alert
        from app.core.config import settings
        from app.core.redis_client import FEED_HEARTBEAT_KEY, FEED_STALE_KEY, get_redis

        if not settings.LIVE_TRADING_ENABLED:
            return

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        market_open = (
            now.weekday() < 5
            and (now.hour > 9 or (now.hour == 9 and now.minute >= 15))
            and (now.hour < 15 or (now.hour == 15 and now.minute <= 30))
        )
        redis = get_redis()
        if not market_open:
            await redis.delete(FEED_STALE_KEY)
            return

        raw = await redis.get(FEED_HEARTBEAT_KEY)
        age = None if not raw else time.time() - float(raw)
        limit = float(settings.FEED_STALE_SEC)
        fresh = age is not None and age <= limit
        if fresh:
            await redis.delete(FEED_STALE_KEY)
            return

        # An idle worker has no quotes. That is not a failed feed, and it must
        # not pause manual orders. Pause only while a live session is running.
        running = False
        for pattern in ("strategy:running:*", "formula:running:*", "terminal:running:*"):
            async for _key in redis.scan_iter(match=pattern, count=20):
                running = True
                break
            if running:
                break
        if not running:
            await redis.delete(FEED_STALE_KEY)
            return

        detail = "no quotes yet" if age is None else f"last quote {int(age)}s ago"
        already = await redis.get(FEED_STALE_KEY)
        await redis.set(FEED_STALE_KEY, detail, ex=180)
        if not already:
            await raise_alert("FEED", f"Live feed stale: {detail}. New orders paused.")

    _run(_check)


# ── Formula strategy executor ─────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, name="tasks.run_formula_strategy")
def run_formula_strategy(self, formula_strategy_id: str):
    """Run a no-code formula strategy with T/SL order manager."""

    async def _execute():
        from app.core.database import AsyncSessionLocal
        from app.services.formula_executor import FormulaStrategyExecutor
        async with AsyncSessionLocal() as db:
            executor = FormulaStrategyExecutor(strategy_id=formula_strategy_id, db=db)
            try:
                await executor.start()
            except Exception as exc:
                logger.error(f"Formula executor error [{formula_strategy_id}]: {exc}")
                raise self.retry(exc=exc, countdown=10)

    _run(_execute)


# ── Terminal engine ───────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, name="tasks.run_terminal")
def run_terminal(self, user_id: str):
    """Run the trading terminal for a user (all active rows simultaneously)."""

    async def _execute():
        from app.core.database import AsyncSessionLocal
        from app.services.terminal_engine import TerminalEngine
        async with AsyncSessionLocal() as db:
            engine = TerminalEngine(user_id=user_id, db=db)
            try:
                await engine.start()
            except Exception as exc:
                logger.error(f"Terminal engine error [{user_id}]: {exc}")
                raise self.retry(exc=exc, countdown=10)

    _run(_execute)


@celery_app.task(name="tasks.renew_dhan_token")
def renew_dhan_token():
    """Renew Dhan access token daily at 8 AM before market opens."""
    async def _renew():
        from app.core.database import AsyncSessionLocal
        from app.core.config import settings
        from app.models.broker import BrokerAccount, BrokerName
        from sqlalchemy import select

        if not settings.DHAN_ACCESS_TOKEN:
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(BrokerAccount).where(
                    BrokerAccount.broker       == BrokerName.dhan,
                    BrokerAccount.paper_trading == False,
                    BrokerAccount.is_active     == True,
                )
            )
            accounts = result.scalars().all()
            for account in accounts:
                from app.broker.dhan import DhanAdapter
                adapter = DhanAdapter(
                    client_id    = settings.DHAN_CLIENT_ID,
                    access_token = settings.DHAN_ACCESS_TOKEN,
                )
                success = await adapter.renew_token()
                logger.info(f"Dhan token renewal for {account.client_id}: {'OK' if success else 'FAILED'}")

    _run(_renew)


@celery_app.task(name="tasks.refresh_instrument_csv")
def refresh_instrument_csv():
    """Download fresh Dhan instrument CSV daily at 8 AM IST."""
    import os, requests

    csv_path = os.path.join(
        os.path.dirname(__file__), "..", "market", "instruments.csv"
    )
    csv_path = os.path.abspath(csv_path)

    try:
        resp = requests.get(
            "https://images.dhan.co/api-data/api-scrip-master-detailed.csv",
            timeout=30,
        )
        if resp.status_code == 200 and len(resp.text) > 1000:
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
            lines = resp.text.count("\n")
            logger.info(f"✅ Instrument CSV refreshed: {lines} rows → {csv_path}")

            # Clear in-memory cache so next search reloads from new file
            import app.api.routes.market as mkt
            mkt._instrument_cache = []
            mkt._cache_loaded_at  = 0
        else:
            logger.error(f"Instrument CSV download failed: HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"Instrument CSV refresh error: {e}")
