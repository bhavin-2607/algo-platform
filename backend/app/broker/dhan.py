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
import socket
import requests
from typing import Optional
from app.core.config import settings
from app.broker.base import BaseBrokerAdapter, OrderRequest, OrderResponse

if getattr(settings, "DHAN_FORCE_IPV4", True):
    try:
        import urllib3.util.connection as urllib_conn
        # Enforce IPv4 on socket creation across urllib3 / requests.
        # Windows 11 dual-stack can otherwise resolve api.dhan.co over IPv6,
        # causing SEBI static IP rejection (DH-905) because Dhan portal whitelists IPv4 only.
        urllib_conn.allowed_gai_family = lambda: socket.AF_INET
    except Exception:
        pass

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


def get_public_ipv4() -> str:
    """Fetch current outbound public IPv4 address to assist Dhan static IP verification."""
    for url in [
        "https://api4.ipify.org?format=json",
        "https://api.ipify.org?format=json",
        "https://ifconfig.me/all.json",
    ]:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                ip = data.get("ip") or data.get("ip_addr")
                if ip and "." in ip:
                    return ip
        except Exception:
            continue
    return "unknown"


def get_public_ipv6() -> Optional[str]:
    """Fetch current outbound public IPv6 address if available."""
    # 1. Direct route probe to Cloudflare Public IPv6
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.settimeout(2.0)
        s.connect(("2606:4700:4700::1111", 80))
        v6 = s.getsockname()[0]
        s.close()
        if v6 and ":" in v6 and not v6.startswith(("fe80", "::1")):
            return v6
    except Exception:
        pass

    # 2. External HTTP lookup fallback
    for url in [
        "https://api64.ipify.org?format=json",
        "https://api6.ipify.org?format=json",
    ]:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                ip = data.get("ip") or data.get("ip_addr")
                if ip and ":" in ip:
                    return ip
        except Exception:
            continue
    return None


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
            "client-id":     self._client_id,
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
                curr_ip = get_public_ipv4()
                logger.info(f"Dhan connected: {self._client_id} (Outgoing IPv4: {curr_ip})")
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
            resp = requests.get(
                f"{DHAN_BASE_URL}/RenewToken",
                headers={
                    "access-token": self._access_token,
                    "dhanClientId": self._client_id,
                    "client-id":    self._client_id,
                    "Accept":       "application/json",
                },
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
                "correlationId":     (order.client_order_id or "algo-platform")[:30],
            }

            resp_raw = _req.post(
                "https://api.dhan.co/v2/orders",
                headers={
                    "access-token": self._access_token,
                    "client-id":    self._client_id,
                    "dhanClientId": self._client_id,
                    "Content-Type": "application/json",
                    "Accept":       "application/json",
                },
                json=payload,
                timeout=10,
            )
            resp = resp_raw.json()
            logger.info(f"Dhan place_order response: {resp}")

            # v2 returns the order itself: {orderId, orderStatus: TRANSIT|PENDING|TRADED}
            data = resp.get("data") if isinstance(resp, dict) and isinstance(resp.get("data"), dict) else {}
            order_id = ""
            order_status = ""
            if isinstance(resp, dict) and not resp.get("errorCode"):
                order_id = str(resp.get("orderId") or data.get("orderId") or "")
                order_status = str(resp.get("orderStatus") or data.get("orderStatus") or "")
            if order_id:
                logger.info(f"Dhan order placed: {order_id} status={order_status or 'TRANSIT'}")
                return OrderResponse(
                    broker_order_id=order_id,
                    status=order_status or "TRANSIT",
                )

            err_code = resp.get("errorCode") if isinstance(resp, dict) else ""
            if err_code == "DH-905":
                detected_ip = get_public_ipv4()
                logger.error(
                    f"Dhan DH-905 (Invalid IP): Outgoing IP mismatch or token invalidation. "
                    f"Detected outgoing IPv4: {detected_ip}. "
                    f"Check: 1) Does '{detected_ip}' match the IP configured in Dhan Web Portal? "
                    f"2) CRITICAL: Did you click 'Generate Access Token' in Dhan portal AFTER setting the IP? "
                    f"Old tokens created prior to IP configuration are rejected with DH-905. "
                    f"Please generate a fresh token, update DHAN_ACCESS_TOKEN in .env, and restart run.bat."
                )
                msg = (
                    f"DH-905 Invalid IP. Outgoing IP: {detected_ip}. "
                    f"Ensure this IP is whitelisted on Dhan portal AND generate a NEW token afterwards."
                )
            else:
                msg = resp.get("remarks") or resp.get("errorMessage") or str(resp) if isinstance(resp, dict) else str(resp or "No response")
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

    def _get_list(self, path: str) -> list:
        """Dhan v2 returns a raw JSON list for orders and positions."""
        resp = requests.get(
            f"{DHAN_BASE_URL}{path}",
            headers={
                "access-token": self._access_token,
                "dhanClientId": self._client_id,
                "Accept": "application/json",
            },
            timeout=10,
        )
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and data.get("status") == "success":
            inner = data.get("data") or []
            return inner if isinstance(inner, list) else []
        logger.error(f"Dhan {path} failed: {data if isinstance(data, dict) else resp.status_code}")
        return []

    async def get_positions(self) -> list:
        try:
            return self._get_list("/positions")
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
            return self._get_list("/orders")
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
