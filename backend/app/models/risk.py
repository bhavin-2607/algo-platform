from sqlalchemy import Column, Float, Integer, Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid


class RiskSettings(Base):
    """
    Persisted risk configuration per UserStrategyMap.
    These values are loaded by the executor at strategy start.
    Can be updated live — executor picks up changes on next tick evaluation.
    """
    __tablename__ = "risk_settings"

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_strategy_map_id  = Column(UUID(as_uuid=True), ForeignKey("user_strategy_map.id"), unique=True, nullable=False)
    
    # Loss controls
    daily_loss_limit      = Column(Float,   default=2000.0)   # ₹ max loss per day
    max_exposure          = Column(Float,   default=50000.0)  # ₹ max single order exposure
    max_quantity          = Column(Integer, default=10)        # max qty per order
    max_consecutive_losses= Column(Integer, default=3)         # kill switch trigger

    # Kill switch
    kill_switch_active    = Column(Boolean, default=False)     # manual override
    
    # Timestamps
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at            = Column(DateTime, default=datetime.utcnow)

    strategy_map = relationship("UserStrategyMap", backref="risk_settings")


class RiskEvent(Base):
    """
    Audit log of risk events — blocked orders, kill switch activations, resets.
    """
    __tablename__ = "risk_events"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    map_id       = Column(UUID(as_uuid=True), ForeignKey("user_strategy_map.id"), nullable=True)
    event_type   = Column(String, nullable=False)  # blocked/killed/reset/limit_changed
    reason       = Column(String, nullable=True)
    value        = Column(Float,  nullable=True)   # e.g. the P&L at time of event
    created_at   = Column(DateTime, default=datetime.utcnow)
