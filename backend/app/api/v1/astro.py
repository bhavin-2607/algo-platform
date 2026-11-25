from datetime import datetime, date
from typing import Optional
import zoneinfo

from fastapi import APIRouter, HTTPException, Query

from app.schemas.astro import (
    AstroMarketSignal,
    IntradayAstroResponse,
    MarketWeekOutlookResponse,
    MoonTransitSnapshot,
)
from app.services.astro_service import (
    get_astro_snapshot,
    get_intraday_windows,
    get_market_week_outlook,
    get_moon_transit_snapshot,
)

router = APIRouter()
IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@router.get("/moon-transit", response_model=MoonTransitSnapshot, summary="Get high-precision Moon transit, Vedic lunar telemetry, and upcoming schedule")
async def get_moon_transit():
    """
    Returns high-precision Vedic Moon transit telemetry:
    - Active Rashi, Sanskrit name, Rashi Lord, DMS degree, total longitude
    - Active Nakshatra, Pada, Nakshatra Lord, KP Sub-Lord
    - Daily speed (deg/day) and DMS formatting
    - Real-time transit clock: Ingress, Egress, % Elapsed, Hours remaining
    - Next Rashi and Lord transition
    - Next 7 upcoming Moon sign transits
    """
    try:
        return get_moon_transit_snapshot()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Moon transit calculation error: {exc}")


@router.get("/snapshot", response_model=AstroMarketSignal, summary="Get current or point-in-time financial astrology snapshot")
async def get_snapshot(
    timestamp_iso: Optional[str] = Query(
        None,
        description="Optional exact ISO 8601 timestamp (e.g. 2026-11-23T09:15:00+05:30)."
    ),
    date_str: Optional[str] = Query(
        None,
        description="Optional date in YYYY-MM-DD format (e.g. 2026-11-16). If provided without timestamp, uses time_mode."
    ),
    time_mode: str = Query(
        "SUNRISE",
        description="Benchmark time when date_str is used: SUNRISE (astronomical sunrise for user location), 09:00 (Pre-Market), or LIVE."
    ),
    lat: float = Query(23.0225, description="Geographic latitude (default: 23.0225 N for Ahmedabad)"),
    lon: float = Query(72.5714, description="Geographic longitude (default: 72.5714 E for Ahmedabad)"),
    city: str = Query("Ahmedabad", description="User preferred location name"),
):
    """
    Returns full planetary telemetry (Lahiri Sidereal mode), 27 Vedic Nakshatras & Padas,
    KP Sub-Lords, pairwise geometric aspect stress scores, and market regime classification.
    Supports user location sunrise (Ahmedabad by default) or Pre-Market 09:00 AM IST for exact Kundli app parity.
    """
    dt: Optional[datetime] = None
    date_obj: Optional[date] = None

    if timestamp_iso:
        try:
            dt = datetime.fromisoformat(timestamp_iso)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid timestamp_iso format: {exc}")
    elif date_str:
        try:
            date_obj = date.fromisoformat(date_str)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date_str format (use YYYY-MM-DD): {exc}")

    try:
        return get_astro_snapshot(
            dt=dt,
            date_obj=date_obj,
            time_mode=time_mode,
            lat=lat,
            lon=lon,
            city_name=city,
        )
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
    time_mode: str = Query(
        "SUNRISE",
        description="Daily benchmark: SUNRISE (astronomical sunrise for user location) or 09:00 (Pre-Market open)."
    ),
    lat: float = Query(23.0225, description="Geographic latitude (default: 23.0225 N for Ahmedabad)"),
    lon: float = Query(72.5714, description="Geographic longitude (default: 72.5714 E for Ahmedabad)"),
    city: str = Query("Ahmedabad", description="User preferred location name"),
):
    """
    Returns Monday-to-Friday market trading days structured across:
    - Previous week (5 trading days, testing/audit)
    - Current week (5 trading days, past days + today + remaining days)
    - Next week (5 trading days, forward cyclical projections)

    Excludes non-trading weekends. Daily positions evaluated at Sunrise for the user's location (Ahmedabad by default) or 09:00 AM.
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
            time_mode=time_mode,
            lat=lat,
            lon=lon,
            city_name=city,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Market-week outlook calculation error: {exc}")


