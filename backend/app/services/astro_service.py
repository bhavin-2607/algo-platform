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
import logging
import math
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
import zoneinfo

logger = logging.getLogger(__name__)

try:
    import swisseph as swe
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    SWISSEPH_AVAILABLE = True
except (ImportError, Exception) as exc:
    swe = None
    SWISSEPH_AVAILABLE = False
    logger.warning("swisseph library not found or failed to load (%s). Install with: pip install pysweph", exc)

SWE_SUN = getattr(swe, "SUN", 0)
SWE_MOON = getattr(swe, "MOON", 1)
SWE_MERCURY = getattr(swe, "MERCURY", 2)
SWE_VENUS = getattr(swe, "VENUS", 3)
SWE_MARS = getattr(swe, "MARS", 4)
SWE_JUPITER = getattr(swe, "JUPITER", 5)
SWE_SATURN = getattr(swe, "SATURN", 6)
SWE_URANUS = getattr(swe, "URANUS", 7)
SWE_NEPTUNE = getattr(swe, "NEPTUNE", 8)
SWE_PLUTO = getattr(swe, "PLUTO", 9)
SWE_MEAN_NODE = getattr(swe, "MEAN_NODE", 10)
SWE_FLG_SIDEREAL = getattr(swe, "FLG_SIDEREAL", 64 * 1024)
SWE_FLG_SPEED = getattr(swe, "FLG_SPEED", 256)
SWE_FLG_MOSEPH = getattr(swe, "FLG_MOSEPH", 4)
SWE_CALC_RISE = getattr(swe, "CALC_RISE", 1)

from app.schemas.astro import (
    AspectDetail,
    AstroMarketSignal,
    IntradayAstroResponse,
    IntradayAstroWindow,
    MarketDayOutlookItem,
    MarketWeekOutlookResponse,
    MoonTransitCurrent,
    MoonTransitScheduleItem,
    MoonTransitSnapshot,
    PlanetTelemetry,
    WeekCategory,
)

logger = logging.getLogger(__name__)

# Timezones
IST = zoneinfo.ZoneInfo("Asia/Kolkata")
UTC = zoneinfo.ZoneInfo("UTC")

# National Stock Exchange (NSE) / Mumbai geographic coordinates (19.0760° N, 72.8777° E)
NSE_GEO = (72.8777, 19.0760, 0.0)

# Default User Location: Ahmedabad, Gujarat, India (23.0225° N, 72.5714° E)
DEFAULT_CITY = "Ahmedabad"
DEFAULT_LAT = 23.0225
DEFAULT_LON = 72.5714

# ── Zodiac Signs (12 Sidereal Signs, 30° each) & Classical Ruling Lords ─────────
RASHI_CONFIGS = [
    {"index": 0, "name_en": "Aries", "name_sa": "Mesha", "lord": "Mars", "element": "Fire"},
    {"index": 1, "name_en": "Taurus", "name_sa": "Vrishabha", "lord": "Venus", "element": "Earth"},
    {"index": 2, "name_en": "Gemini", "name_sa": "Mithuna", "lord": "Mercury", "element": "Air"},
    {"index": 3, "name_en": "Cancer", "name_sa": "Karka", "lord": "Moon", "element": "Water"},
    {"index": 4, "name_en": "Leo", "name_sa": "Simha", "lord": "Sun", "element": "Fire"},
    {"index": 5, "name_en": "Virgo", "name_sa": "Kanya", "lord": "Mercury", "element": "Earth"},
    {"index": 6, "name_en": "Libra", "name_sa": "Tula", "lord": "Venus", "element": "Air"},
    {"index": 7, "name_en": "Scorpio", "name_sa": "Vrishchika", "lord": "Mars", "element": "Water"},
    {"index": 8, "name_en": "Sagittarius", "name_sa": "Dhanu", "lord": "Jupiter", "element": "Fire"},
    {"index": 9, "name_en": "Capricorn", "name_sa": "Makara", "lord": "Saturn", "element": "Earth"},
    {"index": 10, "name_en": "Aquarius", "name_sa": "Kumbha", "lord": "Saturn", "element": "Air"},
    {"index": 11, "name_en": "Pisces", "name_sa": "Meena", "lord": "Jupiter", "element": "Water"},
]

SIGNS = [r["name_en"] for r in RASHI_CONFIGS]
SIGN_LORDS = {r["name_en"]: r["lord"] for r in RASHI_CONFIGS}
RASHI_SANSKRIT = {r["name_en"]: r["name_sa"] for r in RASHI_CONFIGS}

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
    ("Sun", SWE_SUN, 1.2, False),
    ("Moon", SWE_MOON, 1.2, False),
    ("Mercury", SWE_MERCURY, 1.0, True),
    ("Venus", SWE_VENUS, 1.0, True),
    ("Mars", SWE_MARS, 1.5, True),
    ("Jupiter", SWE_JUPITER, 1.5, True),
    ("Saturn", SWE_SATURN, 1.8, True),
    ("Rahu", SWE_MEAN_NODE, 1.5, False),
    ("Uranus", SWE_URANUS, 1.2, False),
    ("Neptune", SWE_NEPTUNE, 1.0, False),
    ("Pluto", SWE_PLUTO, 1.2, False),
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


def _format_speed_dms(speed: float) -> str:
    """Format daily velocity in traditional Vedic degrees/minutes/seconds per day (e.g. +14° 34' 05\"/d)."""
    sign = "+" if speed >= 0 else "-"
    abs_speed = abs(speed)
    deg = int(abs_speed)
    rem = (abs_speed - deg) * 60.0
    minute = int(rem)
    sec = int(round((rem - minute) * 60.0))
    if sec >= 60:
        sec = 0
        minute += 1
    if minute >= 60:
        minute = 0
        deg += 1
    return f"{sign}{deg:02d}° {minute:02d}' {sec:02d}\"/d"


def get_sunrise(
    target_date: date,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
) -> datetime:
    """
    Calculates astronomical Sunrise in Asia/Kolkata (IST) for a given latitude and longitude.
    Defaults to Ahmedabad (23.0225° N, 72.5714° E).
    Uses Swiss Ephemeris analytical Moshier engine.
    """
    if swe is not None:
        try:
            jd = swe.julday(target_date.year, target_date.month, target_date.day, 0.0)
            geopos = (lon, lat, 0.0)
            res, tret = swe.rise_trans(jd, SWE_SUN, SWE_CALC_RISE, geopos, 1013.25, 25.0, SWE_FLG_MOSEPH)
            tjd_rise = tret[0]
            year, month, day, hour_dec = swe.revjul(tjd_rise)
            h = int(hour_dec)
            m = int((hour_dec - h) * 60)
            s = int(round(((hour_dec - h) * 60 - m) * 60))
            if s >= 60:
                s = 0
                m += 1
            if m >= 60:
                m = 0
                h += 1
            dt_ut = datetime(year, month, day, h, m, s, tzinfo=UTC)
            return dt_ut.astimezone(IST)
        except Exception as e:
            logger.warning("Sunrise calculation exception (%s), defaulting to 06:58 IST", e)

    return datetime.combine(target_date, time(6, 58), tzinfo=IST)


def get_mumbai_sunrise(target_date: date) -> datetime:
    """Convenience helper calculating sunrise for Mumbai/NSE coordinates (19.0760° N, 72.8777° E)."""
    return get_sunrise(target_date, lat=19.0760, lon=72.8777)




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
    if swe is not None:
        return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_float)

    # Standard astronomical formula for Julian Day fallback
    a = (14 - dt_utc.month) // 12
    y = dt_utc.year + 4800 - a
    m = dt_utc.month + 12 * a - 3
    jdn = dt_utc.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return float(jdn) + (hour_float - 12.0) / 24.0


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


def get_moon_sidereal_position(dt: datetime) -> Tuple[float, float]:
    """Calculate Moon sidereal longitude (0° to 360°) and daily speed (deg/day) via Swiss Ephemeris."""
    if swe is None:
        return 0.0, 13.176
    jd = _to_julian_day(dt)
    calc_res = swe.calc_ut(jd, SWE_MOON, SWE_FLG_SIDEREAL | SWE_FLG_SPEED | SWE_FLG_MOSEPH)
    res = calc_res[0]
    return res[0] % 360.0, res[3]


def find_moon_crossing(t_start: datetime, t_end: datetime, target_deg: float) -> datetime:
    """Find exact crossing timestamp using bisection search."""
    t1 = t_start
    t2 = t_end
    for _ in range(25):
        tm = t1 + (t2 - t1) / 2
        lon_m, _ = get_moon_sidereal_position(tm)
        diff = (lon_m - target_deg + 180.0) % 360.0 - 180.0
        if abs(diff) < 1e-5:
            return tm
        lon_1, _ = get_moon_sidereal_position(t1)
        diff_1 = (lon_1 - target_deg + 180.0) % 360.0 - 180.0
        if diff_1 * diff <= 0:
            t2 = tm
        else:
            t1 = tm
    return tm


def find_moon_rashi_ingress_egress(dt: datetime) -> Tuple[datetime, datetime]:
    """Find exact ingress and egress times for current Rashi."""
    lon, _ = get_moon_sidereal_position(dt)
    sign_idx = int(lon // 30.0) % 12
    boundary_start = sign_idx * 30.0
    boundary_end = (sign_idx + 1) * 30.0 % 360.0

    # Ingress (crossed boundary_start)
    t_curr = dt
    ingress = dt - timedelta(days=1)
    for _ in range(20):
        t_prev = t_curr - timedelta(hours=6)
        lon_prev, _ = get_moon_sidereal_position(t_prev)
        if int(lon_prev // 30.0) % 12 != sign_idx:
            ingress = find_moon_crossing(t_prev, t_curr, boundary_start)
            break
        t_curr = t_prev

    # Egress (crosses boundary_end)
    t_curr = dt
    egress = dt + timedelta(days=1)
    for _ in range(20):
        t_next = t_curr + timedelta(hours=6)
        lon_next, _ = get_moon_sidereal_position(t_next)
        if int(lon_next // 30.0) % 12 != sign_idx:
            egress = find_moon_crossing(t_curr, t_next, boundary_end)
            break
        t_curr = t_next

    return ingress, egress


def find_moon_nakshatra_ingress_egress(dt: datetime) -> Tuple[datetime, datetime]:
    """Find exact ingress and egress times for current Nakshatra."""
    lon, _ = get_moon_sidereal_position(dt)
    nak_idx = int(lon // SPAN_NAKSHATRA) % 27
    boundary_start = nak_idx * SPAN_NAKSHATRA
    boundary_end = (nak_idx + 1) * SPAN_NAKSHATRA % 360.0

    # Ingress
    t_curr = dt
    ingress = dt - timedelta(hours=12)
    for _ in range(20):
        t_prev = t_curr - timedelta(hours=3)
        lon_prev, _ = get_moon_sidereal_position(t_prev)
        if int(lon_prev // SPAN_NAKSHATRA) % 27 != nak_idx:
            ingress = find_moon_crossing(t_prev, t_curr, boundary_start)
            break
        t_curr = t_prev

    # Egress
    t_curr = dt
    egress = dt + timedelta(hours=12)
    for _ in range(20):
        t_next = t_curr + timedelta(hours=3)
        lon_next, _ = get_moon_sidereal_position(t_next)
        if int(lon_next // SPAN_NAKSHATRA) % 27 != nak_idx:
            egress = find_moon_crossing(t_curr, t_next, boundary_end)
            break
        t_curr = t_next

    return ingress, egress


def compute_moon_transit_current(dt: datetime) -> MoonTransitCurrent:
    """Compute detailed real-time Moon transit telemetry."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    dt_ist = dt.astimezone(IST)

    lon, speed = get_moon_sidereal_position(dt_ist)
    sign_idx = int(lon // 30.0) % 12
    deg_in_sign = lon % 30.0
    rashi_cfg = RASHI_CONFIGS[sign_idx]

    nak_idx = int(lon // SPAN_NAKSHATRA) % 27
    nak_name, nak_lord = NAKSHATRAS[nak_idx]
    pada = min(4, int((lon % SPAN_NAKSHATRA) // SPAN_PADA) + 1)
    _, _, _, kp_sub = compute_kp_sub_lord(lon)

    # Ingress & Egress for Rashi
    r_ingress, r_egress = find_moon_rashi_ingress_egress(dt_ist)
    r_rem_sec = max(0.0, (r_egress - dt_ist).total_seconds())
    r_rem_h = r_rem_sec / 3600.0
    r_rem_str = f"{int(r_rem_h)}h {int((r_rem_h - int(r_rem_h)) * 60)}m"
    r_prog_pct = round(min(100.0, max(0.0, (deg_in_sign / 30.0) * 100.0)), 2)

    next_sign_idx = (sign_idx + 1) % 12
    next_rashi_cfg = RASHI_CONFIGS[next_sign_idx]

    # Ingress & Egress for Nakshatra
    n_ingress, n_egress = find_moon_nakshatra_ingress_egress(dt_ist)
    n_rem_sec = max(0.0, (n_egress - dt_ist).total_seconds())
    n_rem_h = n_rem_sec / 3600.0
    n_rem_str = f"{int(n_rem_h)}h {int((n_rem_h - int(n_rem_h)) * 60)}m"
    deg_in_nak = lon % SPAN_NAKSHATRA
    n_prog_pct = round(min(100.0, max(0.0, (deg_in_nak / SPAN_NAKSHATRA) * 100.0)), 2)

    next_nak_idx = (nak_idx + 1) % 27
    next_nak_name, next_nak_lord = NAKSHATRAS[next_nak_idx]

    return MoonTransitCurrent(
        rashi=rashi_cfg["name_en"],
        rashi_sanskrit=rashi_cfg["name_sa"],
        rashi_lord=rashi_cfg["lord"],
        degree=round(deg_in_sign, 4),
        degree_dms=_format_dms(deg_in_sign),
        total_longitude=round(lon, 4),
        nakshatra=nak_name,
        nakshatra_number=nak_idx + 1,
        nakshatra_lord=nak_lord,
        pada=pada,
        kp_sub_lord=kp_sub,
        daily_speed_deg=round(speed, 4),
        daily_speed_dms=_format_speed_dms(speed),
        rashi_progress_pct=r_prog_pct,
        rashi_ingress_ist=r_ingress.strftime("%Y-%m-%d %H:%M:%S IST"),
        rashi_egress_ist=r_egress.strftime("%Y-%m-%d %H:%M:%S IST"),
        rashi_remaining_hours=round(r_rem_h, 2),
        rashi_remaining_str=r_rem_str,
        next_rashi=next_rashi_cfg["name_en"],
        next_rashi_sanskrit=next_rashi_cfg["name_sa"],
        next_rashi_lord=next_rashi_cfg["lord"],
        nakshatra_progress_pct=n_prog_pct,
        nakshatra_ingress_ist=n_ingress.strftime("%Y-%m-%d %H:%M:%S IST"),
        nakshatra_egress_ist=n_egress.strftime("%Y-%m-%d %H:%M:%S IST"),
        nakshatra_remaining_hours=round(n_rem_h, 2),
        nakshatra_remaining_str=n_rem_str,
        next_nakshatra=next_nak_name,
        next_nakshatra_lord=next_nak_lord,
    )


def get_upcoming_moon_transits(dt: datetime, count: int = 7) -> List[MoonTransitScheduleItem]:
    """Calculate upcoming Moon sign transits for the next N signs."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    dt_ist = dt.astimezone(IST)

    schedule: List[MoonTransitScheduleItem] = []
    _, egress = find_moon_rashi_ingress_egress(dt_ist)

    curr_ingress = egress
    for _ in range(count):
        sample_time = curr_ingress + timedelta(minutes=15)
        lon, _ = get_moon_sidereal_position(sample_time)
        sign_idx = int(lon // 30.0) % 12
        rashi_cfg = RASHI_CONFIGS[sign_idx]
        boundary_end = (sign_idx + 1) * 30.0 % 360.0

        t_search = sample_time
        curr_egress = sample_time + timedelta(days=2.5)
        for _ in range(20):
            t_next = t_search + timedelta(hours=6)
            lon_next, _ = get_moon_sidereal_position(t_next)
            if int(lon_next // 30.0) % 12 != sign_idx:
                curr_egress = find_moon_crossing(t_search, t_next, boundary_end)
                break
            t_search = t_next

        duration = (curr_egress - curr_ingress).total_seconds() / 3600.0
        schedule.append(
            MoonTransitScheduleItem(
                rashi=rashi_cfg["name_en"],
                rashi_sanskrit=rashi_cfg["name_sa"],
                rashi_lord=rashi_cfg["lord"],
                ingress_ist=curr_ingress.strftime("%Y-%m-%d %H:%M:%S IST"),
                egress_ist=curr_egress.strftime("%Y-%m-%d %H:%M:%S IST"),
                duration_hours=round(duration, 2),
            )
        )
        curr_ingress = curr_egress

    return schedule


_MOON_SNAPSHOT_CACHE: dict = {}

def get_moon_transit_snapshot(dt: Optional[datetime] = None) -> MoonTransitSnapshot:
    """Returns cached Moon transit snapshot (recalculated at 60s intervals)."""
    global _MOON_SNAPSHOT_CACHE
    if dt is None:
        dt = datetime.now(IST)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)

    cache_key = dt.strftime("%Y-%m-%d %H:%M")
    if cache_key in _MOON_SNAPSHOT_CACHE:
        return _MOON_SNAPSHOT_CACHE[cache_key]

    current = compute_moon_transit_current(dt)
    upcoming = get_upcoming_moon_transits(dt, count=7)
    snapshot = MoonTransitSnapshot(
        calculated_at_ist=dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        current=current,
        upcoming_schedule=upcoming,
    )

    if len(_MOON_SNAPSHOT_CACHE) > 5:
        _MOON_SNAPSHOT_CACHE.clear()
    _MOON_SNAPSHOT_CACHE[cache_key] = snapshot
    return snapshot


def _get_fallback_telemetry() -> List[PlanetTelemetry]:
    """Fallback telemetry when Swiss Ephemeris is not available."""
    bodies = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Uranus", "Neptune", "Pluto", "Ketu"]
    telemetry = []
    for i, name in enumerate(bodies):
        lon = (i * 30.0) % 360.0
        sign_idx = int(lon // 30.0) % 12
        sign_deg = lon % 30.0
        nak_name, nak_lord, pada, kp_sub = compute_kp_sub_lord(lon)
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
                speed=1.0,
                speed_str="+01° 00' 00\"/d",
                is_retrograde=False,
                is_stationary=False,
            )
        )
    return telemetry


def get_planetary_telemetry(dt: datetime) -> List[PlanetTelemetry]:
    """Calculate sidereal positions, nakshatras, KP sub-lords, and speeds for all 12 bodies."""
    if swe is None:
        return _get_fallback_telemetry()

    jd_ut = _to_julian_day(dt)
    flags = SWE_FLG_SIDEREAL | SWE_FLG_SPEED | SWE_FLG_MOSEPH

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
                speed_str=_format_speed_dms(speed),
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
            speed_str=_format_speed_dms(ketu_speed),
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


def get_astro_snapshot(
    dt: Optional[datetime] = None,
    date_obj: Optional[date] = None,
    time_mode: str = "SUNRISE",
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    city_name: str = DEFAULT_CITY,
    reference_label: Optional[str] = None,
) -> AstroMarketSignal:
    """
    Generate a complete AstroMarketSignal snapshot for a given timestamp or (date, time_mode).
    Time modes:
      - "SUNRISE": Exact astronomical sunrise for user location (default: Ahmedabad 23.0225° N, 72.5714° E).
      - "09:00": Market pre-open benchmark (09:00 AM IST).
      - "LIVE": Current live moment in IST.
    """
    sunrise_dt = None
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        eval_dt = dt
        try:
            sunrise_dt = get_sunrise(eval_dt.date(), lat=lat, lon=lon)
        except Exception:
            sunrise_dt = None
        label = reference_label or eval_dt.strftime("%H:%M:%S IST")
    elif date_obj is not None:
        try:
            sunrise_dt = get_sunrise(date_obj, lat=lat, lon=lon)
        except Exception:
            sunrise_dt = None

        mode_upper = time_mode.upper()
        if mode_upper in ("09:00", "09:00 AM", "MARKET_OPEN"):
            eval_dt = datetime.combine(date_obj, time(9, 0), tzinfo=IST)
            label = reference_label or f"09:00 AM IST (Pre-Market)"
        elif mode_upper == "LIVE":
            eval_dt = datetime.now(IST)
            label = reference_label or f"Live ({eval_dt.strftime('%H:%M:%S IST')})"
        else:  # default SUNRISE
            eval_dt = sunrise_dt if sunrise_dt else datetime.combine(date_obj, time(6, 58), tzinfo=IST)
            sr_str = sunrise_dt.strftime("%H:%M:%S IST") if sunrise_dt else "06:58 IST"
            label = reference_label or f"Sunrise at {city_name} ({sr_str})"
    else:
        eval_dt = datetime.now(IST)
        try:
            sunrise_dt = get_sunrise(eval_dt.date(), lat=lat, lon=lon)
        except Exception:
            sunrise_dt = None
        label = reference_label or f"Live ({eval_dt.strftime('%H:%M:%S IST')})"

    planets = get_planetary_telemetry(eval_dt)
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
    elif net_score <= -0.8:
        regime_bias = "BEARISH_HEADWIND"
    else:
        regime_bias = "NEUTRAL_RANGE"

    moon = next((p for p in planets if p.name == "Moon"), None)
    moon_nak = moon.nakshatra if moon else "Unknown"
    moon_sub = moon.kp_sub_lord if moon else "Unknown"
    moon_transit = compute_moon_transit_current(eval_dt)

    dt_ist = eval_dt.astimezone(IST)
    dt_utc = eval_dt.astimezone(UTC)

    # Observational risk multiplier (for watch gauge display)
    risk_mult = 0.5 if volatility_alert else 1.0

    return AstroMarketSignal(
        timestamp_iso=dt_ist.isoformat(),
        timestamp_utc=dt_utc.isoformat(),
        reference_time_label=label,
        sunrise_time_iso=sunrise_dt.isoformat() if sunrise_dt else None,
        city_name=city_name,
        latitude=lat,
        longitude=lon,
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
        moon_transit=moon_transit,
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

    if swe is None:
        return IntradayAstroResponse(
            date=target_date.isoformat(),
            session_open="09:15 IST",
            session_close="15:30 IST",
            total_windows=0,
            windows=[],
        )

    start_time = datetime.combine(target_date, time(9, 15), tzinfo=IST)
    end_time = datetime.combine(target_date, time(15, 30), tzinfo=IST)

    # Sample in 15-minute intervals to detect shifts
    interval = timedelta(minutes=15)
    current_time = start_time

    def _get_moon_state(t: datetime) -> Tuple[float, str, str]:
        jd = _to_julian_day(t)
        calc_res = swe.calc_ut(jd, SWE_MOON, SWE_FLG_SIDEREAL | SWE_FLG_MOSEPH)
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
    time_mode: str = "SUNRISE",
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    city_name: str = DEFAULT_CITY,
) -> MarketWeekOutlookResponse:
    """
    Computes a market-days (Monday-to-Friday only) astrological timing outlook across:
    - Previous week (Mon-Fri, 5 trading days): Historical audit/testing against past sessions (if include_prev is True)
    - Current week (Mon-Fri, 5 trading days): Past days, today, remaining days of the week
    - Next week (Mon-Fri, 5 trading days): Forward-looking cyclical projections (if include_next is True)

    Evaluates daily baseline at astronomical Sunrise for the user's preferred location (default: Ahmedabad 23.0225° N, 72.5714° E)
    or at 09:00 AM IST if requested. Excludes non-trading weekends (Saturday and Sunday).
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
            sunrise_dt = get_sunrise(d, lat=lat, lon=lon)
            if time_mode.upper() in ("09:00", "09:00 AM", "MARKET_OPEN"):
                eval_dt = datetime.combine(d, time(9, 0), tzinfo=IST)
                label = f"09:00 AM IST ({d.strftime('%d %b')})"
            else:
                eval_dt = sunrise_dt
                label = f"Sunrise at {city_name} ({sunrise_dt.strftime('%H:%M IST')})"

            snap = get_astro_snapshot(eval_dt, lat=lat, lon=lon, city_name=city_name, reference_label=label)
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
                    sunrise_time_str=sunrise_dt.strftime("%H:%M IST"),
                    time_mode=time_mode.upper(),
                    city_name=city_name,
                )
            )

    return MarketWeekOutlookResponse(
        reference_date=ref_date.isoformat(),
        include_previous_week=include_prev,
        include_next_week=include_next,
        time_mode=time_mode.upper(),
        city_name=city_name,
        latitude=lat,
        longitude=lon,
        total_trading_days=len(items),
        days=items,
    )

