from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.core.database import Base


class BacktestRun(Base):
    """Latest result used to block a live start of a losing version."""

    __tablename__ = "backtest_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    engine_class = Column(String, nullable=False)
    version = Column(String, nullable=False, default="1")
    symbol = Column(String, nullable=False)
    timeframe = Column(Integer, nullable=False, default=5)
    passed = Column(Boolean, nullable=False, default=False)
    total_pnl = Column(Float, nullable=False, default=0)
    max_drawdown = Column(Float, nullable=False, default=0)
    trade_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
