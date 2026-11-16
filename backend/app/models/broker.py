from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid
import enum


class BrokerName(str, enum.Enum):
    dhan      = "dhan"
    shoonya   = "shoonya"    # legacy — kept for existing DB rows
    paper     = "paper"


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker  = Column(Enum(BrokerName), nullable=False)
    client_id = Column(String, nullable=False)
    encrypted_access_token = Column(String, nullable=True)
    is_active    = Column(Boolean, default=False)
    paper_trading = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    # Copy Trading Configuration
    account_role       = Column(String, default="CHILD")         # "MASTER" or "CHILD"
    account_name       = Column(String, nullable=True)           # e.g. "Primary Account", "Child 1"
    is_copy_enabled    = Column(Boolean, default=True)           # Active in copy fanout
    fixed_qty_equity   = Column(Integer, default=10)             # Fixed share quantity for cash equity
    fixed_lots_fno     = Column(Integer, default=1)              # Fixed lot count for F&O contracts
    max_loss_limit     = Column(Float, nullable=True)            # Optional daily max loss threshold
    force_market_order = Column(Boolean, default=True)           # Force MARKET order for follower execution

    user = relationship("User", back_populates="broker_accounts")
