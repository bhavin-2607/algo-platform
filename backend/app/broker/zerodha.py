from app.broker.base import BaseBrokerAdapter, OrderRequest, OrderResponse
from kiteconnect import KiteConnect
import logging

logger = logging.getLogger(__name__)


class ZerodhaAdapter(BaseBrokerAdapter):
    def __init__(self, api_key: str, access_token: str):
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    async def connect(self) -> bool:
        try:
            profile = self.kite.profile()
            logger.info(f"Zerodha connected: {profile.get('user_name')}")
            return True
        except Exception as e:
            logger.error(f"Zerodha connect error: {e}")
            return False

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=order.exchange,
                tradingsymbol=order.symbol,
                transaction_type=order.direction,
                quantity=order.quantity,
                order_type=order.order_type,
                price=order.price,
                trigger_price=order.trigger_price,
                product=order.product,
            )
            return OrderResponse(broker_order_id=str(order_id), status="OPEN")
        except Exception as e:
            logger.error(f"Zerodha order error: {e}")
            return OrderResponse(broker_order_id="", status="FAILED", message=str(e))

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            self.kite.cancel_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=broker_order_id,
            )
            return True
        except Exception:
            return False

    async def get_positions(self) -> list:
        return self.kite.positions().get("net", [])

    async def get_holdings(self) -> list:
        return self.kite.holdings()

    async def get_funds(self) -> dict:
        return self.kite.margins()

    async def get_order_status(self, broker_order_id: str) -> dict:
        orders = self.kite.orders()
        for o in orders:
            if str(o["order_id"]) == broker_order_id:
                return o
        return {}
