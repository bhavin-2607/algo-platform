"""
Algo Row Model
==============
Stores symbols added to the automated Algo Trading Window.
Runs automated or manual trades using standard trading formulas on DhanHQ.
"""
from datetime import datetime
import uuid

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class BsaAlgoRow(Base):
    __tablename__ = "bsa_algo_rows"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    symbol            = Column(String, nullable=False)
    exchange          = Column(String, default="NSE")
    segment           = Column(String, default="NSE_EQ")
    token             = Column(String, nullable=True)

    # Trading controls
    is_algo_active    = Column(Boolean, default=False)   # ALGO ON (automated) vs ALGO OFF (manual)
    trade_mode        = Column(String, default="FULL")    # FULL, BUY_ONLY, SELL_ONLY
    entry_type        = Column(String, default="FORMULA") # FORMULA, CUSTOM
    custom_entry      = Column(Float, nullable=True)      # Custom buy trigger price
    quantity          = Column(Integer, default=1)
    number_of_trades  = Column(Integer, default=1)       # 1 to 5 only
    trades_completed  = Column(Integer, default=0)
    target_type       = Column(String, default="TGT1")    # TGT1..TGT5, CUSTOM
    custom_target     = Column(Float, nullable=True)      # User-defined custom target level

    # State tracking
    status            = Column(String, default="IDLE")    # IDLE, WAITING_SIGNAL, IN_POSITION, WAITING_RETURN, COMPLETED, STOPPED_SL
    buy_price         = Column(Float, nullable=True)      # Executed market fill price
    sell_tgt          = Column(Float, nullable=True)      # Target exit price
    stop_loss         = Column(Float, nullable=True)      # SL price
    entry_level       = Column(Float, nullable=True)      # Formula calculated entry price level
    last_signal       = Column(String, nullable=True)     # Last signal seen
    last_order_id     = Column(String, nullable=True)
    pnl               = Column(Float, nullable=True)

    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user              = relationship("User")


class BsaAlgoTradeHistory(Base):
    __tablename__ = "bsa_algo_trade_history"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    row_id           = Column(UUID(as_uuid=True), nullable=True)
    symbol           = Column(String, nullable=False)
    exchange         = Column(String, default="NSE")
    segment          = Column(String, default="NSE_EQ")
    trade_mode       = Column(String, default="FULL")
    quantity         = Column(Integer, default=1)
    entry_price      = Column(Float, nullable=False)
    exit_price       = Column(Float, nullable=False)
    pnl              = Column(Float, nullable=False)
    trades_completed = Column(Integer, default=1)
    number_of_trades = Column(Integer, default=1)
    exit_reason      = Column(String, default="TARGET HIT")
    status           = Column(String, default="COMPLETED")
    order_id         = Column(String, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    closed_at        = Column(DateTime, default=datetime.utcnow)

    user             = relationship("User")

