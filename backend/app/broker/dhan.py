"""
Dhan (DhanHQ) broker adapter — v2 API.

Auth (simplest method for individual traders):
  1. Login to web.dhan.co
  2. My Profile → Access DhanHQ APIs → Generate Access Token (24h validity)
  3. Copy dhanClientId and accessToken to .env

Static IP required for ORDER PLACEMENT only (SEBI mandate).
Data APIs (quotes, positions, holdings) work without IP whitelisting.

Auto-renewal: Call /v2/RenewToken before token expires.
"""
import logging
import requests
from app.broker.base import BaseBrokerAdapter, OrderRequest, OrderResponse

logger = logging.getLogger(__name__)

DHAN_BASE_URL = "https://api.dhan.co/v2"
DHAN_AUTH_URL = "https://auth.dhan.co"

# Exchange mapping
EXCHANGE_MAP = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "BFO": "BSE_FNO",
    "MCX": "MCX_COMM",
    "NSE_EQ":  "NSE_EQ",
    "NSE_FNO": "NSE_FNO",
}

# Product type mapping
PRODUCT_MAP = {
    "MIS":  "INTRA",
    "CNC":  "CNC",
    "NRML": "MARGIN",
    "BO":   "BO",
    "CO":   "CO",
}

# Order type mapping
ORDER_TYPE_MAP = {
    "MARKET": "MARKET",
    "LIMIT":  "LIMIT",
    "SL":     "STOP_LOSS",
    "SL-M":   "STOP_LOSS_MARKET",
}


class DhanAdapter(BaseBrokerAdapter):
    """
    Adapter for Dhan / DhanHQ v2 API.
    Uses simple access-token auth — generate from web.dhan.co daily.
    """

    def __init__(self, client_id: str, access_token: str):
        self._client_id    = client_id
        self._access_token = access_token
        self._connected    = False
        self._dhan         = None

    def _headers(self) -> dict:
        return {
            "access-token":  self._access_token,
            "dhanClientId":  self._client_id,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    def _get_sdk(self):
        """Lazy init dhanhq SDK client using DhanContext (v2.1.0+)."""
        if self._dhan is None:
            try:
                # v2.1.0+ uses DhanContext
                from dhanhq import DhanContext, dhanhq
                ctx = DhanContext(self._client_id, self._access_token)
                self._dhan = dhanhq(ctx)
            except ImportError:
                # fallback for older versions
                from dhanhq import dhanhq
                self._dhan = dhanhq(self._client_id, self._access_token)
        return self._dhan

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Verify token by fetching fund limits."""
        try:
            dhan = self._get_sdk()
            resp = dhan.get_fund_limits()
            if resp and resp.get("status") == "success":
                self._connected = True
                logger.info(f"✅ Dhan connected: {self._client_id}")
                return True
            logger.error(f"Dhan connect failed: {resp}")
            return False
        except Exception as e:
            logger.error(f"Dhan connect error: {e}")
            return False

    async def renew_token(self) -> bool:
        """
        Renew access token for another 24 hours.
        Requires current token to still be active.
        POST https://api.dhan.co/v2/RenewToken
        """
        try:
            resp = requests.post(
                f"{DHAN_BASE_URL}/RenewToken",
                headers=self._headers(),
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "success":
                new_token = data.get("accessToken")
                if new_token:
                    self._access_token = new_token
                    self._dhan = None  # reset SDK with new token
                    logger.info("Dhan token renewed successfully")
                    return True
            logger.error(f"Dhan token renewal failed: {data}")
            return False
        except Exception as e:
            logger.error(f"Dhan renew_token error: {e}")
            return False

    # ── Orders ────────────────────────────────────────────────────────────────

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        try:
            import requests as _req
            from app.core.config import settings

            exchange   = EXCHANGE_MAP.get(order.exchange, "NSE_EQ")
            product    = PRODUCT_MAP.get(order.product, "INTRADAY")
            order_type = ORDER_TYPE_MAP.get(order.order_type, "MARKET")
            txn_type   = "BUY" if order.direction == "BUY" else "SELL"

            payload = {
                "dhanClientId":      self._client_id,
                "transactionType":   txn_type,
                "exchangeSegment":   exchange,
                "productType":       product,
                "orderType":         order_type,
                "validity":          "DAY",
                "securityId":        str(order.symbol),
                "quantity":          int(order.quantity),
                "disclosedQuantity": 0,
                "price":             float(order.price or 0),
                "triggerPrice":      float(order.trigger_price or 0),
                "afterMarketOrder":  False,
                "correlationId":     "algo-platform",
            }

            resp_raw = _req.post(
                "https://api.dhan.co/v2/orders",
                headers={
                    "access-token": self._access_token,
                    "client-id":    self._client_id,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            resp = resp_raw.json()
            logger.info(f"Dhan place_order response: {resp}")

            if resp and resp.get("status") == "success":
                order_id = str(resp.get("data", {}).get("orderId", ""))
                logger.info(f"Dhan order placed: {order_id}")
                return OrderResponse(broker_order_id=order_id, status="OPEN")

            msg = resp.get("remarks", str(resp)) if resp else "No response"
            logger.error(f"Dhan place_order failed: {msg}")
            return OrderResponse(broker_order_id="", status="FAILED", message=msg)

        except Exception as e:
            logger.error(f"Dhan place_order exception: {e}")
            return OrderResponse(broker_order_id="", status="FAILED", message=str(e))

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            dhan = self._get_sdk()
            resp = dhan.cancel_order(broker_order_id)
            return resp and resp.get("status") == "success"
        except Exception as e:
            logger.error(f"Dhan cancel_order error: {e}")
            return False

    # ── Account data ──────────────────────────────────────────────────────────

    async def get_positions(self) -> list:
        try:
            dhan = self._get_sdk()
            resp = dhan.get_positions()
            if resp and resp.get("status") == "success":
                return resp.get("data", []) or []
            return []
        except Exception as e:
            logger.error(f"Dhan get_positions error: {e}")
            return []

    async def get_holdings(self) -> list:
        try:
            dhan = self._get_sdk()
            resp = dhan.get_holdings()
            if resp and resp.get("status") == "success":
                return resp.get("data", []) or []
            return []
        except Exception as e:
            logger.error(f"Dhan get_holdings error: {e}")
            return []

    async def get_funds(self) -> dict:
        try:
            dhan = self._get_sdk()
            resp = dhan.get_fund_limits()
            if resp and resp.get("status") == "success":
                return resp.get("data", {}) or {}
            return {}
        except Exception as e:
            logger.error(f"Dhan get_funds error: {e}")
            return {}

    async def get_order_book(self) -> list:
        try:
            dhan = self._get_sdk()
            resp = dhan.get_order_list()
            if resp and resp.get("status") == "success":
                return resp.get("data", []) or []
            return []
        except Exception as e:
            logger.error(f"Dhan get_order_book error: {e}")
            return []

    async def get_order_status(self, broker_order_id: str) -> dict:
        try:
            dhan = self._get_sdk()
            resp = dhan.get_order_by_id(broker_order_id)
            if resp and resp.get("status") == "success":
                return resp.get("data", {}) or {}
            return {}
        except Exception as e:
            logger.error(f"Dhan get_order_status error: {e}")
            return {}

    # ── Market data ───────────────────────────────────────────────────────────

    async def get_ltp(self, exchange: str, security_id: str) -> float | None:
        """Get last traded price for a single instrument."""
        try:
            dhan         = self._get_sdk()
            dhan_exchange = EXCHANGE_MAP.get(exchange, "NSE_EQ")
            resp = dhan.get_market_quote(
                securities={dhan_exchange: [security_id]}
            )
            if resp and resp.get("status") == "success":
                data = resp.get("data", {})
                key  = f"{dhan_exchange}:{security_id}"
                return data.get(key, {}).get("last_price")
            return None
        except Exception as e:
            logger.error(f"Dhan get_ltp error: {e}")
            return None

    def subscribe_feed(
        self,
        instruments: list[str],
        on_tick,
        on_order_update=None,
    ):
        """
        Subscribe to live WebSocket tick feed via DhanHQ Market Feed.
        instruments: list of "EXCHANGE|SECURITY_ID" e.g. ["NSE|1333", "NSE|26000"]
        """
        try:
            from dhanhq import marketfeed, DhanContext

            ctx = DhanContext(self._client_id, self._access_token)

            dhan_instruments = []
            for inst in instruments:
                parts = inst.split("|")
                if len(parts) == 2:
                    exchange, sec_id = parts
                    dhan_exchange = EXCHANGE_MAP.get(exchange, "NSE_EQ")
                    dhan_instruments.append(
                        (dhan_exchange, str(sec_id), marketfeed.Ticker)
                    )

            if not dhan_instruments:
                logger.warning("No valid instruments to subscribe")
                return

            feed = marketfeed.DhanFeed(
                dhan_context      = ctx,
                instruments       = dhan_instruments,
                subscription_code = marketfeed.Ticker,
                on_ticks          = on_tick,
            )
            feed.run_forever()

        except Exception as e:
            logger.error(f"Dhan subscribe_feed error: {e}")
