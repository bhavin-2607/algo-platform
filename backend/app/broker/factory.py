"""
Broker factory — returns ready-to-use adapter for a given BrokerAccount.
Primary broker: Dhan (DhanHQ)
Paper trading:  always returns PaperTradingAdapter
"""
from app.broker.base import BaseBrokerAdapter
from app.broker.paper import PaperTradingAdapter
from app.broker.dhan import DhanAdapter
from app.core.config import settings
from app.core.trading_mode import assert_live_allowed
from app.models.broker import BrokerAccount, BrokerName


def get_broker_adapter(account: BrokerAccount) -> BaseBrokerAdapter:
    if account.paper_trading:
        return PaperTradingAdapter()

    # Any non-paper adapter requires explicit live enable + credentials
    assert_live_allowed()

    broker = account.broker

    # ── Dhan (primary) ────────────────────────────────────────────────────────
    if broker == BrokerName.dhan:
        client_id = account.client_id or settings.DHAN_CLIENT_ID
        access_token = settings.DHAN_ACCESS_TOKEN
        if account.encrypted_access_token:
            from app.core.security import decrypt_broker_token
            try:
                access_token = decrypt_broker_token(account.encrypted_access_token)
            except Exception as exc:
                raise ValueError(f"Could not decrypt this account's Dhan token: {exc}") from exc
        if not client_id or not access_token:
            raise ValueError("Missing Dhan client id or access token for this account")
        return DhanAdapter(
            client_id    = client_id,
            access_token = access_token,
        )

    raise ValueError(f"Unsupported broker: {broker}. Only Dhan is supported.")
