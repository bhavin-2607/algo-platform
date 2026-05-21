"""
Telegram Notification Service
==============================
Sends alerts to users via Telegram bot when:
  - A copy trade signal is received
  - Kill switch is triggered
  - Daily loss limit is approaching (>80%)
  - Strategy starts/stops
  - Order is filled

Setup:
  1. Create a bot via @BotFather on Telegram
  2. Get the bot token
  3. Each user gets their chat_id by messaging the bot /start
  4. Add TELEGRAM_BOT_TOKEN to .env
  5. Users add their chat_id in Settings → Notifications
"""
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self._enabled  = bool(bot_token and bot_token != "your-telegram-bot-token")

    async def send(self, chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
        if not self._enabled:
            logger.debug(f"Telegram disabled. Would have sent to {chat_id}: {message[:50]}")
            return False
        try:
            url = self.BASE_URL.format(token=self.bot_token)
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(url, json={
                    "chat_id":    chat_id,
                    "text":       message,
                    "parse_mode": parse_mode,
                })
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    # ── Message formatters ────────────────────────────────────────────────────

    async def signal_alert(self, chat_id: str, symbol: str, direction: str,
                           quantity: Optional[int], price: Optional[float],
                           tag: str, auto_executed: bool):
        icon  = "🟢" if direction == "BUY" else "🔴" if direction == "SELL" else "🟡"
        mode  = "✅ Auto-executed" if auto_executed else "🔔 Notify only — manual action needed"
        price_str = f"₹{price:,.2f}" if price else "Market"
        msg = (
            f"{icon} <b>TRADE SIGNAL</b>\n\n"
            f"<b>Symbol:</b>    {symbol}\n"
            f"<b>Direction:</b> {direction}\n"
            f"<b>Quantity:</b>  {quantity or 'N/A'}\n"
            f"<b>Price:</b>     {price_str}\n"
            f"<b>Strategy:</b>  {tag}\n\n"
            f"{mode}"
        )
        await self.send(chat_id, msg)

    async def kill_switch_alert(self, chat_id: str, strategy_name: str, reason: str, daily_pnl: float):
        msg = (
            f"⚠️ <b>KILL SWITCH TRIGGERED</b>\n\n"
            f"<b>Strategy:</b> {strategy_name}\n"
            f"<b>Reason:</b>   {reason}\n"
            f"<b>Daily P&L:</b> ₹{daily_pnl:,.2f}\n\n"
            f"All trading has been halted. Login to reset."
        )
        await self.send(chat_id, msg)

    async def risk_warning(self, chat_id: str, strategy_name: str,
                           daily_pnl: float, limit: float, pct: float):
        msg = (
            f"⚠️ <b>RISK WARNING</b>\n\n"
            f"<b>Strategy:</b> {strategy_name}\n"
            f"<b>Daily Loss:</b> ₹{abs(daily_pnl):,.2f} / ₹{limit:,.2f} ({pct:.0f}%)\n\n"
            f"Approaching daily loss limit. Monitor closely."
        )
        await self.send(chat_id, msg)

    async def strategy_started(self, chat_id: str, strategy_name: str, symbol: str, paper: bool):
        mode = "📄 Paper" if paper else "💰 Live"
        msg = (
            f"▶️ <b>STRATEGY STARTED</b>\n\n"
            f"<b>Strategy:</b> {strategy_name}\n"
            f"<b>Symbol:</b>   {symbol}\n"
            f"<b>Mode:</b>     {mode}"
        )
        await self.send(chat_id, msg)

    async def order_filled(self, chat_id: str, symbol: str, direction: str,
                           quantity: int, fill_price: float, pnl: Optional[float] = None):
        icon = "🟢" if direction == "BUY" else "🔴"
        pnl_str = f"\n<b>P&L:</b> ₹{pnl:+,.2f}" if pnl is not None else ""
        msg = (
            f"{icon} <b>ORDER FILLED</b>\n\n"
            f"<b>Symbol:</b>   {symbol}\n"
            f"<b>Direction:</b>{direction}\n"
            f"<b>Qty:</b>      {quantity}\n"
            f"<b>Price:</b>    ₹{fill_price:,.2f}"
            f"{pnl_str}"
        )
        await self.send(chat_id, msg)


# ── Singleton ─────────────────────────────────────────────────────────────────
_notifier: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        from app.core.config import settings
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        _notifier = TelegramNotifier(bot_token=token)
    return _notifier
