from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass


@dataclass
class OrderRequest:
    symbol: str
    exchange: str
    direction: str = "BUY"        # "BUY" or "SELL"
    quantity: int = 1
    order_type: str = "MARKET"    # "MARKET" or "LIMIT"
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    product: str = "MIS"          # MIS, CNC, NRML
    client_order_id: Optional[str] = None  # stable id for idempotent placement
    side: Optional[str] = None
    product_type: Optional[str] = None
    segment: Optional[str] = None

    def __post_init__(self):
        if self.side:
            self.direction = self.side.upper()
        if self.product_type:
            self.product = self.product_type.upper()


@dataclass
class OrderResponse:
    broker_order_id: str
    status: str
    message: str = ""


class BaseBrokerAdapter(ABC):
    """Unified interface — all broker adapters must implement this."""

    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResponse: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool: ...

    @abstractmethod
    async def get_positions(self) -> list: ...

    @abstractmethod
    async def get_holdings(self) -> list: ...

    @abstractmethod
    async def get_funds(self) -> dict: ...

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> dict: ...
