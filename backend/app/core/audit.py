"""Append-only audit rows. Failures are logged and never block trading."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def write_audit(action: str, detail: str = "", actor: str | None = None) -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.audit import AuditEvent

        async with AsyncSessionLocal() as db:
            db.add(AuditEvent(action=action, detail=detail[:2000], actor=actor))
            await db.commit()
    except Exception as exc:
        logger.warning("Audit write failed [%s]: %s", action, exc)
