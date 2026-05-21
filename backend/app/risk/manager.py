"""Risk management layer — every order must pass through this before execution."""
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    daily_loss_limit: float        # Max cumulative loss in ₹ per day
    max_exposure: float            # Max single-order exposure in ₹
    max_quantity: int              # Max quantity per order
    max_consecutive_losses: int    # Activate kill switch after N losses
    paper_trading: bool = True


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config
        self._daily_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._killed: bool = False

    def check_order(
        self,
        symbol: str,
        quantity: int,
        price: float,
        direction: str,
    ) -> tuple[bool, str]:
        """Returns (allowed, reason). Call before every order."""
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

    @property
    def is_killed(self) -> bool:
        return self._killed

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses
