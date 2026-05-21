"""
Notification Routes
===================
Manages Telegram notification settings per user.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.telegram import get_notifier

router = APIRouter()


class NotificationSettings(BaseModel):
    telegram_chat_id:      str  = ""
    notify_signals:        bool = True
    notify_kills:          bool = True
    notify_fills:          bool = True
    notify_risk_warnings:  bool = True


@router.get("/settings")
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
):
    """Get current notification preferences."""
    return {
        "telegram_chat_id":     getattr(current_user, "telegram_chat_id", "") or "",
        "notify_signals":       getattr(current_user, "notify_signals", True),
        "notify_kills":         getattr(current_user, "notify_kills", True),
        "notify_fills":         getattr(current_user, "notify_fills", True),
        "notify_risk_warnings": getattr(current_user, "notify_risk_warnings", True),
        "telegram_configured":  bool(getattr(current_user, "telegram_chat_id", "")),
    }


@router.put("/settings")
async def update_notification_settings(
    payload: NotificationSettings,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences."""
    current_user.telegram_chat_id     = payload.telegram_chat_id
    current_user.notify_signals       = payload.notify_signals
    current_user.notify_kills         = payload.notify_kills
    current_user.notify_fills         = payload.notify_fills
    current_user.notify_risk_warnings = payload.notify_risk_warnings
    await db.commit()
    return {"status": "updated"}


@router.post("/test")
async def send_test_notification(
    current_user: User = Depends(get_current_user),
):
    """Send a test Telegram message to verify setup."""
    chat_id = getattr(current_user, "telegram_chat_id", "")
    if not chat_id:
        raise HTTPException(status_code=400, detail="No Telegram chat ID configured")

    notifier = get_notifier()
    sent = await notifier.send(
        chat_id,
        f"✅ <b>AlgoTrade notification test</b>\n\nHello <b>{current_user.username}</b>! "
        f"Your Telegram notifications are working correctly.",
    )
    if not sent:
        raise HTTPException(status_code=502, detail="Failed to send — check bot token and chat ID")
    return {"status": "sent"}
