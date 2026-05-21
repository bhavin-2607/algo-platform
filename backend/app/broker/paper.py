"""Paper trading adapter — simulates order execution without real capital."""
from app.broker.base import BaseBrokerAdapter, OrderRequest, OrderResponse
from datetime import datetime
import uuid


class PaperTradingAdapter(BaseBrokerAdapter):
    def __init__(self, initial_balance: float = 100_000):
        self._orders: dict[str, dict] = {}
        self._positions: dict[str, dict] = {}
        self._balance = initial_balance

    async def connect(self) -> bool:
        return True

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        order_id = str(uuid.uuid4())
        assumed_price = order.price or 0.0  # caller should pass LTP for market orders
        value = assumed_price * order.quantity

        self._orders[order_id] = {
            "order_id": order_id,
            "symbol": order.symbol,
            "exchange": order.exchange,
            "direction": order.direction,
            "quantity": order.quantity,
            "price": assumed_price,
            "status": "COMPLETE",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Update paper positions
        key = f"{order.exchange}:{order.symbol}"
        pos = self._positions.get(key, {"quantity": 0, "avg_price": 0.0, "symbol": order.symbol})
        if order.direction == "BUY":
            total_qty = pos["quantity"] + order.quantity
            pos["avg_price"] = (pos["avg_price"] * pos["quantity"] + value) / total_qty if total_qty else 0
            pos["quantity"] = total_qty
        else:
            pos["quantity"] -= order.quantity
        self._positions[key] = pos

        return OrderResponse(broker_order_id=order_id, status="COMPLETE")

    async def cancel_order(self, broker_order_id: str) -> bool:
        if broker_order_id in self._orders:
            self._orders[broker_order_id]["status"] = "CANCELLED"
            return True
        return False

    async def get_positions(self) -> list:
        return [p for p in self._positions.values() if p["quantity"] != 0]

    async def get_holdings(self) -> list:
        return []

    async def get_funds(self) -> dict:
        return {"equity": {"available": {"live_balance": self._balance}}}

    async def get_order_status(self, broker_order_id: str) -> dict:
        return self._orders.get(broker_order_id, {})
