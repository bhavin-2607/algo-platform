from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
from datetime import datetime
import uuid


class UserWatchlist(Base):
    """
    Persists a user's market watchlist symbols across server restarts.
    Each row = one symbol for one user.
    """
    __tablename__ = "user_watchlist"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),)

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    symbol         = Column(String, nullable=False)
    security_id    = Column(String, nullable=False)
    exchange_segment = Column(String, default="NSE_EQ")
    added_at       = Column(DateTime, default=datetime.utcnow)
