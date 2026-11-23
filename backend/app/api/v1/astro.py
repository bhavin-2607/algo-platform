from datetime import datetime, date
from typing import Optional
import zoneinfo

from fastapi import APIRouter, HTTPException, Query

from app.schemas.astro import AstroMarketSignal, IntradayAstroResponse
from app.services.astro_service import get_astro_snapshot, get_intraday_windows

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
