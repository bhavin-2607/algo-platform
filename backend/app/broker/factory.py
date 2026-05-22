"""
Broker factory — returns ready-to-use adapter for a given BrokerAccount.
Primary broker: Dhan (DhanHQ)
Legacy broker:  Shoonya (kept for existing accounts, not shown in UI)
Paper trading:  always returns PaperTradingAdapter
"""
from app.broker.base import BaseBrokerAdapter
from app.broker.paper import PaperTradingAdapter
from app.broker.dhan import DhanAdapter
from app.core.config import settings
from app.models.broker import BrokerAccount, BrokerName


def get_broker_adapter(account: BrokerAccount) -> BaseBrokerAdapter:
    if account.paper_trading:
        return PaperTradingAdapter()

    broker = account.broker

    # ── Dhan (primary) ────────────────────────────────────────────────────────
    if broker == BrokerName.dhan:
        missing = [k for k in ["DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN"]
                   if not getattr(settings, k, None)]
        if missing:
            raise ValueError(f"Missing Dhan credentials in .env: {', '.join(missing)}")
        return DhanAdapter(
            client_id    = settings.DHAN_CLIENT_ID,
            access_token = settings.DHAN_ACCESS_TOKEN,
        )

    # ── Shoonya (legacy — not shown in UI, kept for existing DB rows) ─────────
    if broker == BrokerName.shoonya:
        try:
            from app.broker.shoonya import ShoonyaAdapter
            missing = [k for k in ["SHOONYA_USER_ID","SHOONYA_PASSWORD",
                                    "SHOONYA_TOTP_SECRET","SHOONYA_VENDOR_CODE",
                                    "SHOONYA_API_SECRET"]
                       if not getattr(settings, k, None)]
            if missing:
                raise ValueError(f"Missing Shoonya credentials: {', '.join(missing)}")
            return ShoonyaAdapter(
                user_id     = settings.SHOONYA_USER_ID,
                password    = settings.SHOONYA_PASSWORD,
                totp_secret = settings.SHOONYA_TOTP_SECRET,
                vendor_code = settings.SHOONYA_VENDOR_CODE,
                api_secret  = settings.SHOONYA_API_SECRET,
                imei        = getattr(settings, "SHOONYA_IMEI", "algo-platform-v1"),
            )
        except ImportError:
            raise ValueError("Shoonya adapter not available")

    raise ValueError(f"Unsupported broker: {broker}. Use Dhan.")
