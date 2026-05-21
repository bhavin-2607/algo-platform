from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    trader = "trader"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.trader)
    is_active = Column(Boolean, default=True)
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    webhook_token = Column(String, nullable=True, unique=True)  # for TradingView webhooks
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    broker_accounts = relationship("BrokerAccount", back_populates="user")
    strategy_maps = relationship("UserStrategyMap", back_populates="user")
    trades = relationship("Trade", back_populates="user")
