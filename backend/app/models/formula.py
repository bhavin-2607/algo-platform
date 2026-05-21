from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid
import enum


class FormulaStrategy(Base):
    """
    A no-code strategy defined by plain-text entry/exit conditions.
    Your dad can set these up from the UI — no Python needed.
    """
    __tablename__ = "formula_strategies"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name         = Column(String, nullable=False)
    symbol       = Column(String, nullable=False)     # e.g. RELIANCE
    exchange     = Column(String, default="NSE")
    token        = Column(String, default="2885")     # Shoonya instrument token

    # Conditions (plain text, evaluated by FormulaEvaluator)
    entry_long   = Column(String, nullable=True)   # BUY condition
    entry_short  = Column(String, nullable=True)   # SELL condition (optional)
    exit_long    = Column(String, nullable=True)   # Exit long condition
    exit_short   = Column(String, nullable=True)   # Exit short condition

    # Order settings
    quantity          = Column(Integer, default=1)
    product_type      = Column(String, default="MIS")   # MIS / CNC / NRML
    order_type        = Column(String, default="MARKET") # MARKET / LIMIT
    timeframe_minutes = Column(Integer, default=5)

    # Risk per trade
    target_pct    = Column(Float, nullable=True)   # e.g. 2.0 = 2% profit target
    sl_pct        = Column(Float, nullable=True)   # e.g. 1.0 = 1% stop loss
    trailing_sl   = Column(Boolean, default=False)  # enable trailing SL
    trail_pct     = Column(Float, nullable=True)   # trail by this % from peak

    # State
    is_active     = Column(Boolean, default=False)
    paper_trading = Column(Boolean, default=True)
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=True)

    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user           = relationship("User")
    open_positions = relationship("ManagedPosition", back_populates="strategy",
                                  foreign_keys="ManagedPosition.strategy_id")


class PositionStatus(str, enum.Enum):
    open     = "open"
    closed   = "closed"
    sl_hit   = "sl_hit"
    target_hit = "target_hit"


class ManagedPosition(Base):
    """
    Tracks an open position with Target/SL/Trailing SL.
    One row per active trade — the order manager monitors these.
    """
    __tablename__ = "managed_positions"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id       = Column(UUID(as_uuid=True), ForeignKey("formula_strategies.id"), nullable=True)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False)

    symbol            = Column(String, nullable=False)
    exchange          = Column(String, nullable=False)
    direction         = Column(String, nullable=False)   # BUY / SELL
    quantity          = Column(Integer, nullable=False)
    entry_price       = Column(Float, nullable=False)
    entry_order_id    = Column(String, nullable=True)

    # Risk levels (₹ absolute prices)
    target_price      = Column(Float, nullable=True)
    sl_price          = Column(Float, nullable=True)
    trailing_sl       = Column(Boolean, default=False)
    trail_pct         = Column(Float, nullable=True)
    peak_price        = Column(Float, nullable=True)   # highest LTP seen since entry (for trailing)

    # Exit
    exit_price        = Column(Float, nullable=True)
    exit_order_id     = Column(String, nullable=True)
    pnl               = Column(Float, nullable=True)
    status            = Column(Enum(PositionStatus), default=PositionStatus.open)
    exit_reason       = Column(String, nullable=True)

    is_paper          = Column(Boolean, default=True)
    created_at        = Column(DateTime, default=datetime.utcnow)
    closed_at         = Column(DateTime, nullable=True)

    strategy = relationship("FormulaStrategy", back_populates="open_positions",
                             foreign_keys=[strategy_id])
