"""Risk management layer — every order must pass through this before execution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _today_ist() -> str:
    return datetime.now(IST).date().isoformat()


@dataclass
class RiskConfig:
    daily_loss_limit: float        # Max cumulative loss in ₹ per day
    max_exposure: float            # Max single-order exposure in ₹
    max_quantity: int              # Max quantity per order
    max_consecutive_losses: int    # Activate kill switch after N losses
    paper_trading: bool = True


class RiskManager:
    def __init__(self, config: RiskConfig, map_id: Optional[str] = None):
        self.config = config
        self.map_id = map_id
        self._daily_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._killed: bool = False
        self._day: str = _today_ist()

    async def load(self) -> None:
        """Load persisted state from Redis; reset if trading day rolled over (IST)."""
        if not self.map_id:
            return
        from app.core.redis_client import get_redis, risk_state_key

        redis = get_redis()
        raw = await redis.get(risk_state_key(self.map_id))
        if not raw:
            self._day = _today_ist()
            await self.save()
            return

        try:
            data = json.loads(raw)
        except Exception:
            logger.warning(f"Invalid risk state JSON for {self.map_id}")
            self._day = _today_ist()
            await self.save()
            return

        stored_day = data.get("day") or _today_ist()
        if stored_day != _today_ist():
            logger.info(
                f"Risk day rollover for {self.map_id}: {stored_day} → {_today_ist()}"
            )
            self.reset_daily()
            await self.save()
            return

        self._daily_pnl = float(data.get("daily_pnl", 0.0))
        self._consecutive_losses = int(data.get("consecutive_losses", 0))
        self._killed = bool(data.get("killed", False))
        self._day = stored_day
        logger.info(
            f"Risk loaded {self.map_id}: pnl={self._daily_pnl} "
            f"losses={self._consecutive_losses} killed={self._killed}"
        )

    async def save(self) -> None:
        if not self.map_id:
            return
        from app.core.redis_client import get_redis, risk_state_key

        redis = get_redis()
        payload = json.dumps({
            "daily_pnl":          self._daily_pnl,
            "consecutive_losses": self._consecutive_losses,
            "killed":             self._killed,
            "day":                self._day or _today_ist(),
            "updated_at":         datetime.now(timezone.utc).isoformat(),
        })
        await redis.set(risk_state_key(self.map_id), payload, ex=86400 * 2)

    def check_order(
        self,
        symbol: str,
        quantity: int,
        price: float,
        direction: str,
    ) -> tuple[bool, str]:
        """Returns (allowed, reason). Call before every order."""
        # Auto day reset if clock crossed IST midnight without load()
        if self._day != _today_ist():
            self.reset_daily()

        if self._killed:
            return False, "Emergency kill switch is active"

        if quantity > self.config.max_quantity:
            return False, f"Quantity {quantity} exceeds limit {self.config.max_quantity}"

        exposure = quantity * price
        if exposure > self.config.max_exposure:
            return False, f"Exposure ₹{exposure:,.0f} exceeds limit ₹{self.config.max_exposure:,.0f}"

        if self._daily_pnl <= -self.config.daily_loss_limit:
            return False, f"Daily loss limit ₹{self.config.daily_loss_limit:,.0f} reached"

        return True, "OK"

    def record_trade_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl
        if pnl < 0:
            self._consecutive_losses += 1
            logger.warning(f"Consecutive losses: {self._consecutive_losses}")
            if self._consecutive_losses >= self.config.max_consecutive_losses:
                self._killed = True
                logger.error("Kill switch ACTIVATED after consecutive losses")
        else:
            self._consecutive_losses = 0

    def kill(self) -> None:
        """Manually activate kill switch."""
        self._killed = True
        logger.error("Kill switch manually activated")

    def reset_daily(self) -> None:
        """Call at market open each day."""
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._killed = False
        self._day = _today_ist()

    @property
    def is_killed(self) -> bool:
        return self._killed

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses
