from datetime import datetime, date
from typing import Optional
import zoneinfo

from fastapi import APIRouter, HTTPException, Query

from app.schemas.astro import (
    AstroMarketSignal,
    IntradayAstroResponse,
    MarketWeekOutlookResponse,
)
from app.services.astro_service import (
    get_astro_snapshot,
    get_intraday_windows,
    get_market_week_outlook,
)

router = APIRouter()
IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@router.get("/snapshot", response_model=AstroMarketSignal, summary="Get current or point-in-time financial astrology snapshot")
async def get_snapshot(
    timestamp_iso: Optional[str] = Query(
        None,
        description="Optional ISO 8601 timestamp (e.g. 2026-11-23T09:15:00+05:30). Defaults to current IST time."
    )
):
    """
    Returns full planetary telemetry (Lahiri Sidereal mode), 27 Vedic Nakshatras & Padas,
    KP Sub-Lords, pairwise geometric aspect stress scores, and market regime classification.
    """
    dt: Optional[datetime] = None
    if timestamp_iso:
        try:
            dt = datetime.fromisoformat(timestamp_iso)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid timestamp_iso format: {exc}")
    try:
        return get_astro_snapshot(dt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Astro snapshot calculation error: {exc}")


@router.get("/intraday-windows", response_model=IntradayAstroResponse, summary="Get today's NSE session intraday shift windows")
async def get_windows(
    date_str: Optional[str] = Query(
        None,
        description="Optional date in YYYY-MM-DD format. Defaults to today in IST."
    )
):
    """
    Scans the Indian exchange session (09:15 to 15:30 IST) for Moon Nakshatra transitions (HIGH weight)
    and KP Sub-Lord transitions (MEDIUM/LOW weight).
    """
    target_d: Optional[date] = None
    if date_str:
        try:
            target_d = date.fromisoformat(date_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date_str format (use YYYY-MM-DD): {exc}")
    try:
        return get_intraday_windows(target_d)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Intraday windows calculation error: {exc}")


@router.get(
    "/market-week-outlook",
    response_model=MarketWeekOutlookResponse,
    summary="Get multi-week Monday-to-Friday market timing outlook (previous week, current week, next week)"
)
async def get_week_outlook(
    include_prev: bool = Query(
        True,
        description="Include previous week (Mon-Fri) for historical testing & audit"
    ),
    include_next: bool = Query(
        True,
        description="Include next week (Mon-Fri) for forward-looking cyclical projections"
    ),
    ref_date_str: Optional[str] = Query(
        None,
        description="Optional reference date in YYYY-MM-DD. Defaults to current IST date."
    ),
):
    """
    Returns Monday-to-Friday market trading days structured across:
    - Previous week (5 trading days, testing/audit)
    - Current week (5 trading days, past days + today + remaining days)
    - Next week (5 trading days, forward cyclical projections)

    Excludes non-trading weekends.
    """
    ref_d: Optional[date] = None
    if ref_date_str:
        try:
            ref_d = date.fromisoformat(ref_date_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid ref_date_str format (use YYYY-MM-DD): {exc}")
    try:
        return get_market_week_outlook(
            include_prev=include_prev,
            include_next=include_next,
            ref_date=ref_d,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Market-week outlook calculation error: {exc}")

