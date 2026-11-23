"""
Financial Astrology & Cyclical Market Timing Service (Astro-Timing Engine)
=========================================================================
Computes Lahiri Sidereal planetary telemetry, 27 Vedic Nakshatras & Padas,
Krishnamurti Paddhati (KP) Sub-Lords, pairwise geometric aspect stress scores,
and intraday market session timing windows for the Indian markets (NSE session 09:15-15:30 IST).

Designed for high-precision analytical execution on Linux ARM64 / Docker / macOS
relying on Moshier analytical precision (swe.FLG_MOSEPH) with zero external .se1 files.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
import zoneinfo

import swisseph as swe

from app.schemas.astro import (
    AspectDetail,
    AstroMarketSignal,
    IntradayAstroResponse,
    IntradayAstroWindow,
    MarketDayOutlookItem,
    MarketWeekOutlookResponse,
    PlanetTelemetry,
    WeekCategory,
)

logger = logging.getLogger(__name__)

# Timezones
IST = zoneinfo.ZoneInfo("Asia/Kolkata")
UTC = zoneinfo.ZoneInfo("UTC")

# Initialize Swiss Ephemeris in Lahiri Sidereal mode
swe.set_sid_mode(swe.SIDM_LAHIRI)

# ── Zodiac Signs (12 Sidereal Signs, 30° each) ────────────────────────────────
SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── 27 Vedic Nakshatras (13° 20' = 13.333333333333334° each) ─────────────────
SPAN_NAKSHATRA = 360.0 / 27.0  # 13.333333333333334° (800 arcminutes)
SPAN_PADA = SPAN_NAKSHATRA / 4.0  # 3.3333333333333335° (200 arcminutes)

NAKSHATRAS: List[Tuple[str, str]] = [
    ("Ashwini", "Ketu"),
    ("Bharani", "Venus"),
    ("Krittika", "Sun"),
    ("Rohini", "Moon"),
    ("Mrigashira", "Mars"),
    ("Ardra", "Rahu"),
    ("Punarvasu", "Jupiter"),
    ("Pushya", "Saturn"),
    ("Ashlesha", "Mercury"),
    ("Magha", "Ketu"),
    ("Purva Phalguni", "Venus"),
    ("Uttara Phalguni", "Sun"),
    ("Hasta", "Moon"),
    ("Chitra", "Mars"),
    ("Swati", "Rahu"),
    ("Vishakha", "Jupiter"),
    ("Anuradha", "Saturn"),
    ("Jyeshtha", "Mercury"),
    ("Mula", "Ketu"),
    ("Purva Ashadha", "Venus"),
    ("Uttara Ashadha", "Sun"),
    ("Shravana", "Moon"),
    ("Dhanishta", "Mars"),
    ("Shatabhisha", "Rahu"),
    ("Purva Bhadrapada", "Jupiter"),
    ("Uttara Bhadrapada", "Saturn"),
    ("Revati", "Mercury"),
]

# ── Vimshottari Dasha Cycle & KP Sub-Lord Proportions ─────────────────────────
# Total cycle = 120 years
VIMSHOTTARI_CYCLE = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
VIMSHOTTARI_YEARS: Dict[str, float] = {
    "Ketu": 7.0,
    "Venus": 20.0,
    "Sun": 6.0,
    "Moon": 10.0,
    "Mars": 7.0,
    "Rahu": 18.0,
    "Jupiter": 16.0,
    "Saturn": 19.0,
    "Mercury": 17.0,
}
TOTAL_VIMSHOTTARI_YEARS = 120.0

# Benefic vs Malefic classifications for market impact rating
BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
MALEFICS = {"Saturn", "Mars", "Rahu", "Ketu", "Sun"}

# ── Planetary Tracking Configuration ──────────────────────────────────────────
# (name, swe_id, base_power, can_be_stationary)
PLANET_CONFIGS = [
    ("Sun", swe.SUN, 1.2, False),
    ("Moon", swe.MOON, 1.2, False),
    ("Mercury", swe.MERCURY, 1.0, True),
    ("Venus", swe.VENUS, 1.0, True),
    ("Mars", swe.MARS, 1.5, True),
    ("Jupiter", swe.JUPITER, 1.5, True),
    ("Saturn", swe.SATURN, 1.8, True),
    ("Rahu", swe.MEAN_NODE, 1.5, False),
    ("Uranus", swe.URANUS, 1.2, False),
    ("Neptune", swe.NEPTUNE, 1.0, False),
    ("Pluto", swe.PLUTO, 1.2, False),
]

# ── Aspect Rules (Ptolemaic Aspects & Maximum Orbs) ───────────────────────────
ASPECT_SPECS = [
    ("CONJUNCTION", 0.0, 6.0),
    ("SEXTILE", 60.0, 4.0),
    ("SQUARE", 90.0, 5.0),
    ("TRINE", 120.0, 5.0),
    ("OPPOSITION", 180.0, 6.0),
]


def _format_dms(deg: float) -> str:
    """Format degrees into D° M' S\" string."""
    d = int(deg)
    rem_m = (deg - d) * 60.0
    m = int(rem_m)
    s = int(round((rem_m - m) * 60.0))
    if s >= 60:
        s = 0
        m += 1
    if m >= 60:
        m = 0
        d += 1
    return f"{d}° {m:02d}' {s:02d}\""


def _to_julian_day(dt: datetime) -> float:
    """Convert a timezone-aware or naive datetime to Julian Day (UT)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    dt_utc = dt.astimezone(UTC)
    hour_float = (
        dt_utc.hour
        + dt_utc.minute / 60.0
        + dt_utc.second / 3600.0
        + dt_utc.microsecond / 3600000000.0
    )
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_float)


def compute_kp_sub_lord(lon: float) -> Tuple[str, str, int, str]:
    """
    Given a sidereal longitude (0° to 360°), compute:
      - Nakshatra Name
      - Nakshatra Lord
      - Pada (1 to 4)
      - Krishnamurti Paddhati (KP) Sub-Lord
    """
    normalized_lon = lon % 360.0
    nak_idx = int(normalized_lon // SPAN_NAKSHATRA) % 27
    nak_pos = normalized_lon % SPAN_NAKSHATRA  # 0° to 13° 20'
    pada = min(4, int(nak_pos // SPAN_PADA) + 1)

    nak_name, nak_lord = NAKSHATRAS[nak_idx]

    # In KP Astrology, the first sub of any Nakshatra is ruled by the Nakshatra Lord itself.
    # The subsequent 8 subs follow the Vimshottari cycle cyclically.
    start_idx = VIMSHOTTARI_CYCLE.index(nak_lord)
    sub_sequence = [VIMSHOTTARI_CYCLE[(start_idx + i) % 9] for i in range(9)]

    # Locate the active Sub-Lord by cumulative arc length
    cum_arc = 0.0
    kp_sub_lord = sub_sequence[0]
    for sub in sub_sequence:
        sub_arc = (VIMSHOTTARI_YEARS[sub] / TOTAL_VIMSHOTTARI_YEARS) * SPAN_NAKSHATRA
        if nak_pos < cum_arc + sub_arc or math.isclose(nak_pos, cum_arc + sub_arc, abs_tol=1e-7):
            kp_sub_lord = sub
            break
        cum_arc += sub_arc

    return nak_name, nak_lord, pada, kp_sub_lord


def get_planetary_telemetry(dt: datetime) -> List[PlanetTelemetry]:
    """Calculate sidereal positions, nakshatras, KP sub-lords, and speeds for all 12 bodies."""
    jd_ut = _to_julian_day(dt)
    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED | swe.FLG_MOSEPH

    telemetry: List[PlanetTelemetry] = []
    rahu_lon = 0.0
    rahu_speed = 0.0

    # 1. Primary bodies from Swiss Ephemeris
    for name, swe_id, base_power, can_be_stationary in PLANET_CONFIGS:
        calc_res = swe.calc_ut(jd_ut, swe_id, flags)
        res = calc_res[0]
        lon = res[0] % 360.0
        speed = res[3]  # daily velocity in degrees/day

        if name == "Rahu":
            rahu_lon = lon
            rahu_speed = speed

        sign_idx = int(lon // 30.0) % 12
        sign_deg = lon % 30.0
        nak_name, nak_lord, pada, kp_sub = compute_kp_sub_lord(lon)

        is_retrograde = speed < 0.0
        is_stationary = can_be_stationary and (abs(speed) < 0.05)

        telemetry.append(
            PlanetTelemetry(
                name=name,
                longitude=round(lon, 4),
                sign=SIGNS[sign_idx],
                sign_degree=round(sign_deg, 4),
                sign_degree_str=_format_dms(sign_deg),
                nakshatra=nak_name,
                nakshatra_lord=nak_lord,
                pada=pada,
                kp_sub_lord=kp_sub,
                speed=round(speed, 4),
                is_retrograde=is_retrograde,
                is_stationary=is_stationary,
            )
        )

    # 2. Ketu (South Node) is derived as exactly 180° opposite Rahu
    ketu_lon = (rahu_lon + 180.0) % 360.0
    ketu_speed = rahu_speed
    ketu_sign_idx = int(ketu_lon // 30.0) % 12
    ketu_sign_deg = ketu_lon % 30.0
    k_nak, k_lord, k_pada, k_sub = compute_kp_sub_lord(ketu_lon)

    telemetry.append(
        PlanetTelemetry(
            name="Ketu",
            longitude=round(ketu_lon, 4),
            sign=SIGNS[ketu_sign_idx],
            sign_degree=round(ketu_sign_deg, 4),
            sign_degree_str=_format_dms(ketu_sign_deg),
            nakshatra=k_nak,
            nakshatra_lord=k_lord,
            pada=k_pada,
            kp_sub_lord=k_sub,
            speed=round(ketu_speed, 4),
            is_retrograde=True,
            is_stationary=False,
        )
    )

    return telemetry


def compute_active_aspects(planets: List[PlanetTelemetry]) -> List[AspectDetail]:
    """Calculate all active geometric aspects and stress/harmony weights."""
    planet_map = {p.name: p for p in planets}
    powers = {cfg[0]: cfg[2] for cfg in PLANET_CONFIGS}
    powers["Ketu"] = 1.5

    active: List[AspectDetail] = []
    n = len(planets)

    for i in range(n):
        for j in range(i + 1, n):
            p1 = planets[i]
            p2 = planets[j]

            diff = abs(p1.longitude - p2.longitude) % 360.0
            sep = min(diff, 360.0 - diff)

            for asp_name, target_deg, max_orb in ASPECT_SPECS:
                orb = abs(sep - target_deg)
                if orb <= max_orb:
                    intensity = max(0.0, 1.0 - (orb / max_orb))
                    base_power = (powers.get(p1.name, 1.0) + powers.get(p2.name, 1.0)) / 2.0
                    weight = round(intensity * base_power, 3)

                    # Hard aspect classification:
                    # Squares (90°) and Oppositions (180°) are hard aspects.
                    # Conjunctions (0°) involving malefics (Mars, Saturn, Rahu, Ketu, Pluto, Uranus) are hard.
                    # Sextiles (60°) and Trines (120°) are soft aspects.
                    if asp_name in ("SQUARE", "OPPOSITION"):
                        is_hard = True
                    elif asp_name == "CONJUNCTION":
                        is_hard = (
                            p1.name in ("Mars", "Saturn", "Rahu", "Ketu", "Pluto", "Uranus")
                            or p2.name in ("Mars", "Saturn", "Rahu", "Ketu", "Pluto", "Uranus")
                        )
                    else:
                        is_hard = False

                    desc = f"{p1.name} {asp_name.title()} {p2.name} (orb {orb:.2f}°)"
                    active.append(
                        AspectDetail(
                            body_a=p1.name,
                            body_b=p2.name,
                            aspect_type=asp_name,
                            target_deg=target_deg,
                            separation_deg=round(sep, 2),
                            orb_deg=round(orb, 2),
                            is_hard=is_hard,
                            weight=weight,
                            description=desc,
                        )
                    )

    active.sort(key=lambda a: a.weight, reverse=True)
    return active


def get_astro_snapshot(dt: Optional[datetime] = None) -> AstroMarketSignal:
    """Generate a complete AstroMarketSignal snapshot for a given time (defaults to current IST)."""
    if dt is None:
        dt = datetime.now(IST)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)

    planets = get_planetary_telemetry(dt)
    aspects = compute_active_aspects(planets)

    hard_score = round(sum(a.weight for a in aspects if a.is_hard), 2)
    soft_score = round(sum(a.weight for a in aspects if not a.is_hard), 2)
    net_score = round(soft_score - hard_score, 2)

    stationary = [p.name for p in planets if p.is_stationary]
    volatility_alert = (hard_score >= 1.8) or (len(stationary) > 0)

    if volatility_alert:
        regime_bias = "HIGH_VOLATILITY_CAUTION"
    elif net_score >= 0.8:
        regime_bias = "BULLISH_TAILWIND"
    else:
        regime_bias = "NEUTRAL_RANGE"

    moon = next((p for p in planets if p.name == "Moon"), None)
    moon_nak = moon.nakshatra if moon else "Unknown"
    moon_sub = moon.kp_sub_lord if moon else "Unknown"

    dt_ist = dt.astimezone(IST)
    dt_utc = dt.astimezone(UTC)

    # Observational risk multiplier (for watch gauge display)
    risk_mult = 0.5 if volatility_alert else 1.0

    return AstroMarketSignal(
        timestamp_iso=dt_ist.isoformat(),
        timestamp_utc=dt_utc.isoformat(),
        regime_bias=regime_bias,
        volatility_alert=volatility_alert,
        hard_aspect_score=hard_score,
        soft_aspect_score=soft_score,
        net_sentiment_score=net_score,
        moon_nakshatra=moon_nak,
        moon_kp_sub_lord=moon_sub,
        stationary_planets=stationary,
        planets=planets,
        active_aspects=aspects,
        risk_multiplier=risk_mult,
    )


def get_astro_risk_multiplier(dt: Optional[datetime] = None) -> float:
    """Informational/watch multiplier helper: returns 0.5 during volatility alert, 1.0 normally."""
    snap = get_astro_snapshot(dt)
    return 0.5 if snap.volatility_alert else 1.0


def get_intraday_windows(target_date: Optional[date] = None) -> IntradayAstroResponse:
    """
    Scans the Indian exchange trading session (09:15 to 15:30 IST) for the given date,
    detecting exact timestamps where the Moon changes Nakshatra or KP Sub-Lord.
    """
    if target_date is None:
        target_date = datetime.now(IST).date()

    start_time = datetime.combine(target_date, time(9, 15), tzinfo=IST)
    end_time = datetime.combine(target_date, time(15, 30), tzinfo=IST)

    # Sample in 15-minute intervals to detect shifts
    interval = timedelta(minutes=15)
    current_time = start_time

    def _get_moon_state(t: datetime) -> Tuple[float, str, str]:
        jd = _to_julian_day(t)
        calc_res = swe.calc_ut(jd, swe.MOON, swe.FLG_SIDEREAL | swe.FLG_MOSEPH)
        res = calc_res[0]
        lon = res[0] % 360.0
        nak, _, _, sub = compute_kp_sub_lord(lon)
        return lon, nak, sub

    prev_lon, prev_nak, prev_sub = _get_moon_state(start_time)
    windows: List[IntradayAstroWindow] = []

    # Minute-by-minute refinement helper when a transition is found
    def _find_exact_minute(t_start: datetime, t_end: datetime, check_type: str) -> datetime:
        low = t_start
        high = t_end
        target_val = _get_moon_state(high)[1 if check_type == "NAK" else 2]
        best_t = high
        # Binary search down to minute precision (4 iterations covers 15 min)
        for _ in range(5):
            mid = low + (high - low) / 2
            mid_val = _get_moon_state(mid)[1 if check_type == "NAK" else 2]
            if mid_val == target_val:
                best_t = mid
                high = mid
            else:
                low = mid
        return best_t.replace(second=0, microsecond=0)

    while current_time <= end_time:
        next_time = min(current_time + interval, end_time)
        curr_lon, curr_nak, curr_sub = _get_moon_state(next_time)

        # 1. Check Moon Nakshatra Shift (HIGH weight)
        if curr_nak != prev_nak:
            exact_t = _find_exact_minute(current_time, next_time, "NAK")
            windows.append(
                IntradayAstroWindow(
                    timestamp=exact_t.isoformat(),
                    time_str=exact_t.strftime("%H:%M IST"),
                    event_type="MOON_NAKSHATRA_SHIFT",
                    from_entity=prev_nak,
                    to_entity=curr_nak,
                    weight="HIGH",
                    description=f"Moon shifted Nakshatra from {prev_nak} to {curr_nak}. Major cyclical market inflection window.",
                )
            )

        # 2. Check KP Sub-Lord Shift (MEDIUM or LOW weight)
        if curr_sub != prev_sub:
            exact_t = _find_exact_minute(current_time, next_time, "SUB")
            # If changing from malefic to benefic or vice versa, it has MEDIUM weight
            from_is_benefic = prev_sub in BENEFICS
            to_is_benefic = curr_sub in BENEFICS
            weight = "MEDIUM" if (from_is_benefic != to_is_benefic) else "LOW"

            tone = "benefic expansion" if to_is_benefic else "malefic contraction"
            windows.append(
                IntradayAstroWindow(
                    timestamp=exact_t.isoformat(),
                    time_str=exact_t.strftime("%H:%M IST"),
                    event_type="KP_SUB_LORD_SHIFT",
                    from_entity=prev_sub,
                    to_entity=curr_sub,
                    weight=weight,
                    description=f"Moon transitioned KP Sub-Lord from {prev_sub} to {curr_sub} ({tone}).",
                )
            )

        prev_lon, prev_nak, prev_sub = curr_lon, curr_nak, curr_sub
        if next_time >= end_time:
            break
        current_time = next_time

    # Sort windows chronologically
    windows.sort(key=lambda w: w.timestamp)

    return IntradayAstroResponse(
        date=target_date.isoformat(),
        session_open="09:15 IST",
        session_close="15:30 IST",
        total_windows=len(windows),
        windows=windows,
    )


def get_market_week_outlook(
    include_prev: bool = True,
    include_next: bool = True,
    ref_date: Optional[date] = None,
) -> MarketWeekOutlookResponse:
    """
    Computes a market-days (Monday-to-Friday only) astrological timing outlook across:
    - Previous week (Mon-Fri, 5 trading days): Historical audit/testing against past sessions (if include_prev is True)
    - Current week (Mon-Fri, 5 trading days): Past days, today, remaining days of the week
    - Next week (Mon-Fri, 5 trading days): Forward-looking cyclical projections (if include_next is True)

    Excludes non-trading weekends (Saturday and Sunday).
    """
    now_ist = datetime.now(IST)
    if ref_date is None:
        ref_date = now_ist.date()

    # Calculate Monday of the current week (weekday(): 0=Mon ... 6=Sun)
    curr_monday = ref_date - timedelta(days=ref_date.weekday())
    today_date = now_ist.date()

    trading_blocks: List[Tuple[List[date], WeekCategory]] = []

    if include_prev:
        prev_monday = curr_monday - timedelta(days=7)
        prev_days = [prev_monday + timedelta(days=i) for i in range(5)]
        trading_blocks.append((prev_days, WeekCategory.PREVIOUS_WEEK))

    curr_days = [curr_monday + timedelta(days=i) for i in range(5)]
    trading_blocks.append((curr_days, WeekCategory.CURRENT_WEEK))

    if include_next:
        next_monday = curr_monday + timedelta(days=7)
        next_days = [next_monday + timedelta(days=i) for i in range(5)]
        trading_blocks.append((next_days, WeekCategory.NEXT_WEEK))

    items: List[MarketDayOutlookItem] = []

    for days_list, category in trading_blocks:
        for d in days_list:
            midday_dt = datetime.combine(d, time(12, 0), tzinfo=IST)
            snap = get_astro_snapshot(midday_dt)
            win_res = get_intraday_windows(d)

            items.append(
                MarketDayOutlookItem(
                    date=d.isoformat(),
                    day_name=d.strftime("%a"),
                    day_of_week=d.weekday(),
                    week_category=category,
                    is_today=(d == today_date),
                    regime_bias=snap.regime_bias,
                    volatility_alert=snap.volatility_alert,
                    hard_aspect_score=snap.hard_aspect_score,
                    soft_aspect_score=snap.soft_aspect_score,
                    net_sentiment_score=snap.net_sentiment_score,
                    moon_nakshatra=snap.moon_nakshatra,
                    moon_kp_sub_lord=snap.moon_kp_sub_lord,
                    total_shift_windows=win_res.total_windows,
                )
            )

    return MarketWeekOutlookResponse(
        reference_date=ref_date.isoformat(),
        include_previous_week=include_prev,
        include_next_week=include_next,
        total_trading_days=len(items),
        days=items,
    )

