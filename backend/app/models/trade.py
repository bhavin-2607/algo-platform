from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Enum, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid
import enum


class TradeDirection(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, enum.Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"))
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True)
    symbol = Column(String, nullable=False)
    exchange = Column(String, nullable=False)
    direction = Column(Enum(TradeDirection))
    quantity = Column(Integer)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    strategy_tag = Column(String, nullable=True)
    exit_reason = Column(String, nullable=True)   # TARGET_HIT / SL_HIT / MANUAL / SIGNAL
    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING)
    broker_order_id = Column(String, nullable=True)
    is_paper = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="trades")
