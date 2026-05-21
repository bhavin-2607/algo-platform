"""
Broker factory — given a BrokerAccount ORM object, returns a ready-to-use
adapter instance. Paper trading always returns PaperTradingAdapter regardless
of the broker chosen, so no real credentials are needed during development.
"""
from app.broker.base import BaseBrokerAdapter
from app.broker.paper import PaperTradingAdapter
from app.broker.shoonya import ShoonyaAdapter
from app.broker.dhan import DhanAdapter
from app.core.config import settings
from app.models.broker import BrokerAccount, BrokerName


def get_broker_adapter(account: BrokerAccount) -> BaseBrokerAdapter:
    if account.paper_trading:
        return PaperTradingAdapter()

    broker = account.broker

    if broker == BrokerName.dhan:
        missing = [k for k in ["DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN"]
                   if not getattr(settings, k, None)]
        if missing:
            raise ValueError(f"Missing Dhan credentials in .env: {', '.join(missing)}")
        return DhanAdapter(
            client_id    = settings.DHAN_CLIENT_ID,
            access_token = settings.DHAN_ACCESS_TOKEN,
        )

    if broker == BrokerName.shoonya:
        missing = [k for k in ["SHOONYA_USER_ID","SHOONYA_PASSWORD","SHOONYA_TOTP_SECRET",
                                "SHOONYA_VENDOR_CODE","SHOONYA_API_SECRET"]
                   if not getattr(settings, k, None)]
        if missing:
            raise ValueError(
                f"Missing Shoonya credentials in .env: {', '.join(missing)}"
            )
        return ShoonyaAdapter(
            user_id     = settings.SHOONYA_USER_ID,
            password    = settings.SHOONYA_PASSWORD,
            totp_secret = settings.SHOONYA_TOTP_SECRET,
            vendor_code = settings.SHOONYA_VENDOR_CODE,
            api_secret  = settings.SHOONYA_API_SECRET,
            imei        = getattr(settings, "SHOONYA_IMEI", "algo-platform-v1"),
        )

    raise ValueError(f"Unsupported broker: {broker}")
