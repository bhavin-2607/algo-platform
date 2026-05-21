from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid
import enum


class StrategyStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    stopped = "stopped"


class Strategy(Base):
    """
    Admin-managed table of available strategies.
    `engine_class` maps to a Python class in strategy/registry.py.
    This column is NEVER returned via user-facing APIs.
    """
    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String)
    engine_class = Column(String, nullable=False)   # server-side only
    default_params = Column(JSON, default={})
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_maps = relationship("UserStrategyMap", back_populates="strategy")


class UserStrategyMap(Base):
    """Links a user to a strategy + broker account with custom params."""
    __tablename__ = "user_strategy_map"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"))
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"))
    params = Column(JSON, default={})
    status = Column(Enum(StrategyStatus), default=StrategyStatus.stopped)
    paper_trading = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="strategy_maps")
    strategy = relationship("Strategy", back_populates="user_maps")
