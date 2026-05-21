from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid
import enum


class TerminalRowStatus(str, enum.Enum):
    idle        = "idle"
    watching    = "watching"   # subscribed, evaluating signals
    entry_pending = "entry_pending"
    active      = "active"     # in a position
    exit_pending  = "exit_pending"
    closed      = "closed"


class TerminalRow(Base):
    """
    One row in the trading terminal — equivalent to one row in the Excel sheet.
    Each row watches one symbol and runs hidden server-side entry/exit formulas.
    Formulas are set by admin/leader and never exposed to follower users.
    """
    __tablename__ = "terminal_rows"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id          = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=True)

    # Instrument
    symbol            = Column(String, nullable=False)
    exchange          = Column(String, default="NSE")
    token             = Column(String, nullable=True)   # Shoonya instrument token

    # Hidden formulas (admin-only, never returned to non-admin users)
    entry_formula     = Column(String, nullable=True)
    exit_formula      = Column(String, nullable=True)
    # Optional: custom label shown to user instead of formula
    strategy_label    = Column(String, nullable=True)

    # Trade config
    quantity          = Column(Integer, default=1)
    product_type      = Column(String, default="MIS")   # MIS / CNC / NRML
    order_type        = Column(String, default="MARKET")
    trade_mode        = Column(String, default="PAPER")  # PAPER / REAL

    # Risk per trade
    target_pct        = Column(Float, nullable=True)
    sl_pct            = Column(Float, nullable=True)
    trailing_sl       = Column(Boolean, default=False)
    trail_pct         = Column(Float, nullable=True)

    # Auto-trade or manual approval
    auto_execute      = Column(Boolean, default=True)

    # State
    status            = Column(Enum(TerminalRowStatus), default=TerminalRowStatus.idle)
    is_active         = Column(Boolean, default=False)
    row_order         = Column(Integer, default=0)   # display order

    # Live data cache (updated by tick feed, stored for reconnect)
    last_ltp          = Column(Float, nullable=True)
    last_signal       = Column(String, nullable=True)   # BUY / SELL / HOLD

    # Current position
    entry_price       = Column(Float, nullable=True)
    entry_order_id    = Column(String, nullable=True)
    current_sl        = Column(Float, nullable=True)
    current_target    = Column(Float, nullable=True)
    peak_price        = Column(Float, nullable=True)
    pnl               = Column(Float, nullable=True)

    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User")
