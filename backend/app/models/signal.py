from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Enum, Integer, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid
import enum


class SignalDirection(str, enum.Enum):
    BUY  = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"  # close any open position


class SignalStatus(str, enum.Enum):
    received  = "received"   # webhook hit, not yet processed
    executing = "executing"  # being fanned out to followers
    done      = "done"       # all follower orders placed
    failed    = "failed"     # processing error


class Signal(Base):
    """
    Incoming trade signal from TradingView webhook.
    One Signal → many SignalExecution rows (one per follower).
    """
    __tablename__ = "signals"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    leader_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    symbol       = Column(String, nullable=False)
    exchange     = Column(String, nullable=False, default="NSE")
    direction    = Column(Enum(SignalDirection), nullable=False)
    quantity     = Column(Integer, nullable=True)   # None = use follower's own qty setting
    price        = Column(Float, nullable=True)
    strategy_tag = Column(String, nullable=True)    # e.g. "MA_CROSS", "RSI_OB"
    raw_payload  = Column(JSON, nullable=True)      # full webhook body for debugging
    status       = Column(Enum(SignalStatus), default=SignalStatus.received)
    created_at   = Column(DateTime, default=datetime.utcnow)

    executions = relationship("SignalExecution", back_populates="signal")
    leader     = relationship("User", foreign_keys=[leader_id])


class SignalExecution(Base):
    """
    Tracks how a signal was executed for one specific follower.
    """
    __tablename__ = "signal_executions"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id         = Column(UUID(as_uuid=True), ForeignKey("signals.id"), nullable=False)
    follower_id       = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=True)
    broker_order_id   = Column(String, nullable=True)
    quantity          = Column(Integer, nullable=True)
    fill_price        = Column(Float, nullable=True)
    status            = Column(String, default="pending")  # pending/filled/failed/skipped
    error_msg         = Column(String, nullable=True)
    is_paper          = Column(Boolean, default=True)
    created_at        = Column(DateTime, default=datetime.utcnow)

    signal   = relationship("Signal", back_populates="executions")
    follower = relationship("User", foreign_keys=[follower_id])


class CopyRelationship(Base):
    """
    Links a follower to a leader. Controls auto-execute and qty multiplier.
    """
    __tablename__ = "copy_relationships"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    leader_id         = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    follower_id       = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=True)
    auto_execute      = Column(Boolean, default=True)   # False = notify only
    qty_multiplier    = Column(Float, default=1.0)       # e.g. 0.5 = half leader qty
    is_active         = Column(Boolean, default=True)
    created_at        = Column(DateTime, default=datetime.utcnow)

    leader   = relationship("User", foreign_keys=[leader_id])
    follower = relationship("User", foreign_keys=[follower_id])
