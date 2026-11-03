"""Gauges Prometheus scrapes from the API. Values live in Redis so the worker and the API share them."""
from __future__ import annotations

import logging

from prometheus_client import REGISTRY
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector

from app.core.config import settings
from app.core.redis_client import FEED_STALE_KEY, LIVE_KILL_KEY

logger = logging.getLogger(__name__)

ORDER_REJECTS_KEY = "metrics:alert:ORDER"


def snapshot_from_values(stale: bool, kill: bool, order_rejects: int) -> dict:
    return {
        "feed_stale": 1 if stale else 0,
        "live_kill": 1 if kill else 0,
        "order_rejects": max(0, int(order_rejects)),
    }


def read_ops_snapshot() -> dict:
    try:
        import redis

        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=1)
        stale = bool(client.get(FEED_STALE_KEY))
        kill = bool(client.get(LIVE_KILL_KEY))
        raw = client.get(ORDER_REJECTS_KEY)
        rejects = int(raw or 0)
        return snapshot_from_values(stale, kill, rejects)
    except Exception as exc:
        logger.warning("Ops metrics read failed: %s", exc)
        return snapshot_from_values(False, False, 0)


class OpsCollector(Collector):
    def collect(self):
        snap = read_ops_snapshot()
        stale = GaugeMetricFamily("algo_feed_stale", "1 when the feed watchdog has paused new entries")
        stale.add_metric([], snap["feed_stale"])
        yield stale
        kill = GaugeMetricFamily("algo_live_kill", "1 when the global live kill switch is on")
        kill.add_metric([], snap["live_kill"])
        yield kill
        rejects = CounterMetricFamily("algo_order_rejects", "Live order rejects recorded since Redis was last cleared")
        rejects.add_metric([], snap["order_rejects"])
        yield rejects


def register_ops_metrics() -> None:
    if getattr(register_ops_metrics, "_done", False):
        return
    REGISTRY.register(OpsCollector())
    register_ops_metrics._done = True
