"""One stop, target, and trail calculation for engines, formulas, and the terminal."""
from __future__ import annotations


def protective_prices(
    direction: str,
    price: float,
    sl_pct: float = 0.5,
    target_pct: float = 1.0,
    sl: float | None = None,
    target: float | None = None,
) -> tuple[float, float]:
    """Absolute stop and target. An explicit price wins over a percent."""
    side = (direction or "BUY").upper()
    if sl is not None:
        sl_price = float(sl)
    elif side == "BUY":
        sl_price = round(price * (1 - sl_pct / 100), 2)
    else:
        sl_price = round(price * (1 + sl_pct / 100), 2)

    if target is not None:
        target_price = float(target)
    elif side == "BUY":
        target_price = round(price * (1 + target_pct / 100), 2)
    else:
        target_price = round(price * (1 - target_pct / 100), 2)
    return sl_price, target_price


def trail_stop(
    direction: str,
    ltp: float,
    peak: float | None,
    current_sl: float | None,
    trail_pct: float,
) -> tuple[float, float | None]:
    """Move the stop only in the trade's favor. Returns (peak, new_sl or None if unchanged)."""
    side = (direction or "BUY").upper()
    peak = peak if peak is not None else ltp
    if side == "BUY":
        if ltp <= peak:
            return peak, None
        new_sl = round(ltp * (1 - trail_pct / 100), 2)
        if current_sl is not None and new_sl <= current_sl:
            return ltp, None
        return ltp, new_sl

    if ltp >= peak:
        return peak, None
    new_sl = round(ltp * (1 + trail_pct / 100), 2)
    if current_sl is not None and new_sl >= current_sl:
        return ltp, None
    return ltp, new_sl


def live_start_block_reason(
    *,
    paper: bool,
    live_enabled: bool,
    catalogue_version: str,
    code_version: str,
    pinned_version: str | None,
    params_ok: bool,
) -> str | None:
    """Why a start or assignment must be refused. None means it may proceed."""
    if not params_ok:
        return "Strategy parameters failed validation"
    if paper:
        return None
    if not live_enabled:
        return "This strategy version is not enabled for live trading"
    if str(catalogue_version) != str(code_version):
        return (
            f"Catalogue version {catalogue_version} does not match "
            f"the loaded engine version {code_version}"
        )
    if pinned_version and str(pinned_version) != str(catalogue_version):
        return (
            f"This assignment is pinned to version {pinned_version}, "
            f"and the catalogue is version {catalogue_version}"
        )
    return None
