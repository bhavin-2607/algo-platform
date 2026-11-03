"""Operator alerts: log, a short Redis list, and Telegram when configured."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

ALERTS_KEY = "alerts:recent"


async def raise_alert(kind: str, message: str) -> None:
    logger.error("ALERT %s: %s", kind, message)
    payload = json.dumps({
        "kind": kind,
        "message": message,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        from app.core.redis_client import get_redis

        redis = get_redis()
        await redis.lpush(ALERTS_KEY, payload)
        await redis.ltrim(ALERTS_KEY, 0, 99)
    except Exception as exc:
        logger.warning("Alert redis write failed: %s", exc)

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""
    if not token or not chat_id:
        return
    try:
        from app.services.telegram import TelegramNotifier

        await TelegramNotifier(token).send(chat_id, f"{kind}: {message}")
    except Exception as exc:
        logger.warning("Alert telegram send failed: %s", exc)
