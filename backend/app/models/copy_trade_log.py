from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import uuid


class CopyTradeLog(Base):
    """
    Audit log of every order executed across master and child accounts
    during copy trading fan-out.
    """
    __tablename__ = "copy_trade_logs"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id            = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    batch_id           = Column(String, nullable=False, index=True)   # Groups master + child orders for same trigger
    broker_account_id  = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False)
    account_role       = Column(String, nullable=False)               # MASTER or CHILD
    account_name       = Column(String, nullable=True)
    symbol             = Column(String, nullable=False)
    exchange           = Column(String, nullable=False, default="NSE")
    direction          = Column(String, nullable=False)               # BUY or SELL
    order_type         = Column(String, nullable=False, default="MARKET")
    requested_quantity = Column(Integer, nullable=False)
    filled_quantity    = Column(Integer, default=0)
    fill_price         = Column(Float, nullable=True)
    broker_order_id    = Column(String, nullable=True)
    status             = Column(String, nullable=False)               # FILLED, REJECTED, PENDING, SKIPPED
    error_message      = Column(String, nullable=True)
    source             = Column(String, default="MANUAL")             # ALGO, WATCHLIST, MANUAL, KILL
    created_at         = Column(DateTime, default=datetime.utcnow)

    broker_account = relationship("BrokerAccount")
    user           = relationship("User")
