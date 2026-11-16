from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class DhanAccountCreate(BaseModel):
    client_id: str
    access_token: str
    account_name: Optional[str] = None
    account_role: Optional[str] = "CHILD"       # MASTER or CHILD
    paper_trading: Optional[bool] = False
    is_copy_enabled: Optional[bool] = True
    fixed_qty_equity: Optional[int] = 10
    fixed_lots_fno: Optional[int] = 1
    max_loss_limit: Optional[float] = None
    force_market_order: Optional[bool] = True


class DhanAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    account_role: Optional[str] = None
    is_copy_enabled: Optional[bool] = None
    paper_trading: Optional[bool] = None
    fixed_qty_equity: Optional[int] = None
    fixed_lots_fno: Optional[int] = None
    max_loss_limit: Optional[float] = None
    force_market_order: Optional[bool] = None
    access_token: Optional[str] = None


class DhanAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    broker: str
    client_id: str
    account_role: str
    account_name: Optional[str] = None
    is_active: bool
    is_copy_enabled: bool
    paper_trading: bool
    fixed_qty_equity: int
    fixed_lots_fno: int
    max_loss_limit: Optional[float] = None
    force_market_order: bool
    available_margin: Optional[float] = 0.0
    live_pnl: Optional[float] = 0.0
    token_valid: Optional[bool] = True
    created_at: datetime


class CopyTradeLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: str
    broker_account_id: UUID
    account_role: str
    account_name: Optional[str] = None
    symbol: str
    exchange: str
    direction: str
    order_type: str
    requested_quantity: int
    filled_quantity: int
    fill_price: Optional[float] = None
    broker_order_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    source: str
    created_at: datetime


class CopyTradingSummaryResponse(BaseModel):
    master_account: Optional[DhanAccountResponse] = None
    child_accounts: List[DhanAccountResponse] = []
    total_child_count: int = 0
    active_copy_count: int = 0
    is_copy_system_active: bool = True
