"""
Shoonya (Finvasia) broker adapter using the official NorenRestApiPy client.

Shoonya API docs: https://github.com/Shoonya-Dev/ShoonyaApi-py
NorenRestApiPy PyPI: https://pypi.org/project/NorenRestApiPy/

Credentials required (all stored encrypted in DB / env):
  - user_id       : Shoonya client ID
  - password      : Shoonya login password
  - totp_secret   : TOTP secret for 2FA (use pyotp to generate token at login time)
  - vendor_code   : API vendor code from Shoonya
  - api_secret    : API secret from Shoonya
  - imei          : any string, e.g. "abc1234" (used as device fingerprint)
"""

import hashlib
import logging
import pyotp

from NorenRestApiPy.NorenApi import NorenApi
from app.broker.base import BaseBrokerAdapter, OrderRequest, OrderResponse

logger = logging.getLogger(__name__)

# Shoonya production endpoints
SHOONYA_HOST      = "https://api.shoonya.com/NorenWClientTP/"
SHOONYA_WEBSOCKET = "wss://api.shoonya.com/NorenWSTP/"

# Product type mapping  (our internal name → Shoonya code)
PRODUCT_MAP = {
    "MIS": "I",   # Intraday
    "CNC": "C",   # Cash-and-carry / delivery
    "NRML": "M",  # Normal (F&O carry-forward)
    "BO": "B",    # Bracket order
    "CO": "H",    # Cover order
}

# Price type mapping
PRICE_TYPE_MAP = {
    "MARKET": "MKT",
    "LIMIT":  "LMT",
    "SL":     "SL-LMT",
    "SL-M":   "SL-MKT",
}


class ShoonyaAdapter(BaseBrokerAdapter):
    """
    Adapter wrapping NorenApi for Shoonya / Finvasia.
    All methods are async-compatible (blocking calls run synchronously;
    wrap in asyncio.to_thread if needed for high-concurrency deployments).
    """

    def __init__(
        self,
        user_id: str,
        password: str,
        totp_secret: str,
        vendor_code: str,
        api_secret: str,
        imei: str = "algo-platform-v1",
    ):
        self._user_id     = user_id
        self._password    = password
        self._totp_secret = totp_secret
        self._vendor_code = vendor_code
        self._api_secret  = api_secret
        self._imei        = imei
        self._connected   = False

        self.api = NorenApi(host=SHOONYA_HOST, websocket=SHOONYA_WEBSOCKET)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _totp(self) -> str:
        """Generate current TOTP token from the stored secret."""
        return pyotp.TOTP(self._totp_secret).now()

    # ── Connection ───────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Log in to Shoonya.  The password must be SHA-256 hashed before sending.
        The twoFA field is the current 6-digit TOTP token.
        """
        try:
            response = self.api.login(
                userid=self._user_id,
                password=self._sha256(self._password),
                twoFA=self._totp(),
                vendor_code=self._vendor_code,
                api_secret=self._sha256(self._api_secret),
                imei=self._imei,
            )
            if response and response.get("stat") == "Ok":
                self._connected = True
                logger.info(f"Shoonya connected: {response.get('uname', self._user_id)}")
                return True

            logger.error(f"Shoonya login failed: {response}")
            return False
        except Exception as e:
            logger.error(f"Shoonya connect error: {e}")
            return False

    # ── Orders ───────────────────────────────────────────────────────────────

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        try:
            price_type = PRICE_TYPE_MAP.get(order.order_type, "MKT")
            product    = PRODUCT_MAP.get(order.product, "I")

            response = self.api.place_order(
                buy_or_sell  = "B" if order.direction == "BUY" else "S",
                product_type = product,
                exchange     = order.exchange,
                tradingsymbol= order.symbol,
                quantity     = order.quantity,
                discloseqty  = 0,
                price_type   = price_type,
                price        = order.price or 0.0,
                trigger_price= order.trigger_price,
                retention    = "DAY",
                remarks      = "algo-platform",
            )

            if response and response.get("stat") == "Ok":
                order_no = response.get("norenordno", "")
                logger.info(f"Shoonya order placed: {order_no}")
                return OrderResponse(broker_order_id=order_no, status="OPEN")

            msg = response.get("emsg", "Unknown error") if response else "No response"
            logger.error(f"Shoonya place_order failed: {msg}")
            return OrderResponse(broker_order_id="", status="FAILED", message=msg)

        except Exception as e:
            logger.error(f"Shoonya place_order exception: {e}")
            return OrderResponse(broker_order_id="", status="FAILED", message=str(e))

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            response = self.api.cancel_order(orderno=broker_order_id)
            if response and response.get("stat") == "Ok":
                return True
            logger.error(f"Shoonya cancel failed: {response}")
            return False
        except Exception as e:
            logger.error(f"Shoonya cancel_order exception: {e}")
            return False

    # ── Account data ─────────────────────────────────────────────────────────

    async def get_positions(self) -> list:
        try:
            response = self.api.get_positions()
            # Shoonya returns None when there are no open positions
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(f"Shoonya get_positions error: {e}")
            return []

    async def get_holdings(self) -> list:
        try:
            response = self.api.get_holdings(product_type="C")
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(f"Shoonya get_holdings error: {e}")
            return []

    async def get_funds(self) -> dict:
        try:
            response = self.api.get_limits()
            return response or {}
        except Exception as e:
            logger.error(f"Shoonya get_funds error: {e}")
            return {}

    async def get_order_status(self, broker_order_id: str) -> dict:
        try:
            response = self.api.single_order_history(orderno=broker_order_id)
            # Returns a list of order state snapshots; last entry = latest
            if isinstance(response, list) and response:
                return response[-1]
            return {}
        except Exception as e:
            logger.error(f"Shoonya get_order_status error: {e}")
            return {}

    # ── Market data (bonus — not on base interface but useful for strategies) ─

    def get_quotes(self, exchange: str, token: str) -> dict:
        """Fetch live quote for a scrip. token = Shoonya instrument token."""
        try:
            return self.api.get_quotes(exchange=exchange, token=token) or {}
        except Exception as e:
            logger.error(f"Shoonya get_quotes error: {e}")
            return {}

    def subscribe_feed(
        self,
        instruments: list[str],
        on_tick,
        on_order_update=None,
    ):
        """
        Subscribe to live WebSocket tick feed.

        instruments: list of "EXCHANGE|TOKEN" strings, e.g. ["NSE|26000", "BSE|500325"]
        on_tick:     callback(tick_data: dict)
        """
        def _on_open():
            for inst in instruments:
                self.api.subscribe(inst)

        self.api.start_websocket(
            subscribe_callback=on_tick,
            order_update_callback=on_order_update,
            socket_open_callback=_on_open,
        )
