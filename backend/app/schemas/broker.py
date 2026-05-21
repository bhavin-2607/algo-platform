from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.broker import BrokerName


class BrokerConnectRequest(BaseModel):
    """User submits this to link a broker account."""
    broker: BrokerName
    client_id: str
    paper_trading: bool = True   # default to paper — user must explicitly go live


class BrokerAccountResponse(BaseModel):
    id: UUID
    broker: BrokerName
    client_id: str
    is_active: bool
    paper_trading: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BrokerStatusResponse(BaseModel):
    is_active: bool
    message: str


class PositionItem(BaseModel):
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float


class FundsResponse(BaseModel):
    available_cash: float
    used_margin: float
    raw: dict
