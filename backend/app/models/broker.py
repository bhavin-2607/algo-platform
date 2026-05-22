from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum
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

    user = relationship("User", back_populates="broker_accounts")
