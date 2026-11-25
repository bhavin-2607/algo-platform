from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class WeekCategory(str, Enum):
    PREVIOUS_WEEK = "PREVIOUS_WEEK"
    CURRENT_WEEK = "CURRENT_WEEK"
    NEXT_WEEK = "NEXT_WEEK"


class MoonTransitCurrent(BaseModel):
    rashi: str = Field(..., description="English Rashi name (e.g. Taurus)")
    rashi_sanskrit: str = Field(..., description="Sanskrit Rashi name (e.g. Vrishabha)")
    rashi_lord: str = Field(..., description="Ruling planet of Rashi (e.g. Venus)")
    degree: float = Field(..., description="Exact degree in sign (0.00 to 29.99)")
    degree_dms: str = Field(..., description="Formatted DMS string (e.g. 21° 35' 08\")")
    total_longitude: float = Field(..., description="Total sidereal longitude (0° to 360°)")
    nakshatra: str = Field(..., description="Nakshatra name (e.g. Rohini)")
    nakshatra_number: int = Field(..., ge=1, le=27, description="Nakshatra index (1 to 27)")
    nakshatra_lord: str = Field(..., description="Nakshatra ruler (e.g. Moon)")
    pada: int = Field(..., ge=1, le=4, description="Nakshatra Pada (1 to 4)")
    kp_sub_lord: str = Field(..., description="KP Sub-Lord (e.g. Saturn)")
    daily_speed_deg: float = Field(..., description="Moon speed in deg/day")
    daily_speed_dms: str = Field(..., description="Formatted DMS speed per day")
    rashi_progress_pct: float = Field(..., description="Progression through sign (0% to 100%)")
    rashi_ingress_ist: str = Field(..., description="IST timestamp when Moon entered this Rashi")
    rashi_egress_ist: str = Field(..., description="IST timestamp when Moon exits to next Rashi")
    rashi_remaining_hours: float = Field(..., description="Hours remaining in current Rashi")
    rashi_remaining_str: str = Field(..., description="Remaining time formatted (e.g. 13h 21m)")
    next_rashi: str = Field(..., description="Next Rashi to be transited")
    next_rashi_sanskrit: str = Field(..., description="Sanskrit name of next Rashi")
    next_rashi_lord: str = Field(..., description="Lord of next Rashi")
    nakshatra_progress_pct: float = Field(..., description="Progression through Nakshatra (0% to 100%)")
    nakshatra_ingress_ist: str = Field(..., description="IST timestamp when Moon entered this Nakshatra")
    nakshatra_egress_ist: str = Field(..., description="IST timestamp when Moon exits to next Nakshatra")
    nakshatra_remaining_hours: float = Field(..., description="Hours remaining in current Nakshatra")
    nakshatra_remaining_str: str = Field(..., description="Remaining time formatted in Nakshatra")
    next_nakshatra: str = Field(..., description="Next Nakshatra to be transited")
    next_nakshatra_lord: str = Field(..., description="Lord of next Nakshatra")


class MoonTransitScheduleItem(BaseModel):
    rashi: str = Field(..., description="English Rashi name")
    rashi_sanskrit: str = Field(..., description="Sanskrit Rashi name")
    rashi_lord: str = Field(..., description="Rashi Lord")
    ingress_ist: str = Field(..., description="Ingress timestamp in IST")
    egress_ist: str = Field(..., description="Egress timestamp in IST")
    duration_hours: float = Field(..., description="Total transit duration in hours")


class MoonTransitSnapshot(BaseModel):
    calculated_at_ist: str = Field(..., description="Calculation timestamp in IST")
    current: MoonTransitCurrent = Field(..., description="Current Moon transit telemetry")
    upcoming_schedule: List[MoonTransitScheduleItem] = Field(default_factory=list, description="Upcoming Moon sign transits")


class PlanetTelemetry(BaseModel):
    name: str = Field(..., description="Planetary body name (e.g. Sun, Moon, Mars, Saturn)")
    longitude: float = Field(..., description="Sidereal longitude (0° to 360°)")
    sign: str = Field(..., description="Vedic Zodiac sign (e.g. Aries, Taurus)")
    sign_degree: float = Field(..., description="Degree within sign (0° to 30°)")
    sign_degree_str: str = Field(..., description="Formatted degree: e.g. 14° 28' 12\"")
    nakshatra: str = Field(..., description="Vedic Nakshatra name (1 to 27)")
    nakshatra_lord: str = Field(..., description="Lord of the Nakshatra (Vimshottari ruler)")
    pada: int = Field(..., ge=1, le=4, description="Nakshatra Pada (quarter, 1 to 4)")
    kp_sub_lord: str = Field(..., description="Krishnamurti Paddhati (KP) Sub-Lord")
    speed: float = Field(..., description="Apparent daily velocity in degrees per day")
    speed_str: str = Field(..., description="Daily speed formatted in DMS: e.g. +14° 34' 05\"/d")
    is_retrograde: bool = Field(..., description="True if apparent daily speed is negative")
    is_stationary: bool = Field(..., description="True if speed is nearly zero (|speed| < 0.05 deg/day)")


class AspectDetail(BaseModel):
    body_a: str = Field(..., description="First celestial body")
    body_b: str = Field(..., description="Second celestial body")
    aspect_type: str = Field(..., description="Aspect type: CONJUNCTION, SEXTILE, SQUARE, TRINE, OPPOSITION")
    target_deg: float = Field(..., description="Exact angle of the aspect (0, 60, 90, 120, 180)")
    separation_deg: float = Field(..., description="Actual angular separation between bodies")
    orb_deg: float = Field(..., description="Deviation from exact aspect angle")
    is_hard: bool = Field(..., description="True for stress/tension aspects (Square, Opposition, Malefic Conjunction)")
    weight: float = Field(..., description="Calculated intensity score based on orb and planetary power")
    description: str = Field(..., description="Human-readable aspect summary")


class AstroMarketSignal(BaseModel):
    timestamp_iso: str = Field(..., description="ISO 8601 timestamp in Asia/Kolkata (IST)")
    timestamp_utc: str = Field(..., description="ISO 8601 timestamp in UTC")
    reference_time_label: str = Field("Live IST", description="Time label (e.g. Sunrise 06:46 IST, 09:00 AM IST, Live)")
    sunrise_time_iso: Optional[str] = Field(None, description="ISO timestamp of astronomical sunrise for user location")
    city_name: str = Field("Ahmedabad", description="User preferred city (default: Ahmedabad)")
    latitude: float = Field(23.0225, description="Geographic latitude (default: 23.0225 N)")
    longitude: float = Field(72.5714, description="Geographic longitude (default: 72.5714 E)")
    regime_bias: str = Field(..., description="BULLISH_TAILWIND, BEARISH_HEADWIND, HIGH_VOLATILITY_CAUTION, or NEUTRAL_RANGE")
    volatility_alert: bool = Field(..., description="True if hard aspects >= 1.8 or any major planet is stationary")
    hard_aspect_score: float = Field(..., description="Cumulative stress score from hard aspects")
    soft_aspect_score: float = Field(..., description="Cumulative harmony score from soft aspects")
    net_sentiment_score: float = Field(..., description="Soft score minus Hard score (positive=tailwind, negative=stress)")
    moon_nakshatra: str = Field(..., description="Current Vedic Nakshatra of the Moon")
    moon_kp_sub_lord: str = Field(..., description="Current KP Sub-Lord of the Moon")
    stationary_planets: List[str] = Field(default_factory=list, description="List of currently stationary planets")
    planets: List[PlanetTelemetry] = Field(..., description="Telemetry for all tracked celestial bodies")
    active_aspects: List[AspectDetail] = Field(default_factory=list, description="Currently active geometric aspects")
    risk_multiplier: float = Field(1.0, description="Observational risk gauge (0.5 for volatility alert, 1.0 normal)")
    moon_transit: Optional[MoonTransitCurrent] = Field(None, description="Detailed Moon Transit telemetry")


class IntradayAstroWindow(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 timestamp in Asia/Kolkata (IST)")
    time_str: str = Field(..., description="Formatted clock time (HH:MM IST)")
    event_type: str = Field(..., description="MOON_NAKSHATRA_SHIFT or KP_SUB_LORD_SHIFT")
    from_entity: str = Field(..., description="Prior Nakshatra or KP Sub-Lord")
    to_entity: str = Field(..., description="New Nakshatra or KP Sub-Lord")
    weight: str = Field(..., description="Impact level: HIGH, MEDIUM, or LOW")
    description: str = Field(..., description="Summary of astrological market shift")


class IntradayAstroResponse(BaseModel):
    date: str = Field(..., description="Date of the session in YYYY-MM-DD")
    session_open: str = Field("09:15 IST", description="NSE session open")
    session_close: str = Field("15:30 IST", description="NSE session close")
    total_windows: int = Field(..., description="Number of detected boundary shift windows")
    windows: List[IntradayAstroWindow] = Field(..., description="Chronological shift events")


class MarketDayOutlookItem(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD")
    day_name: str = Field(..., description="Day abbreviation: Mon, Tue, Wed, Thu, Fri")
    day_of_week: int = Field(..., ge=0, le=4, description="0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri")
    week_category: WeekCategory = Field(..., description="PREVIOUS_WEEK, CURRENT_WEEK, or NEXT_WEEK")
    is_today: bool = Field(..., description="True if this is the active trading day")
    regime_bias: str = Field(..., description="BULLISH_TAILWIND, BEARISH_HEADWIND, HIGH_VOLATILITY_CAUTION, or NEUTRAL_RANGE")
    volatility_alert: bool = Field(..., description="True if volatility alert is triggered")
    hard_aspect_score: float = Field(..., description="Cumulative stress score from hard aspects")
    soft_aspect_score: float = Field(..., description="Cumulative harmony score from soft aspects")
    net_sentiment_score: float = Field(..., description="Net sentiment score (Soft minus Hard)")
    moon_nakshatra: str = Field(..., description="Moon Nakshatra at reference benchmark")
    moon_kp_sub_lord: str = Field(..., description="Moon KP Sub-Lord at reference benchmark")
    total_shift_windows: int = Field(..., description="Total Moon Nakshatra & KP Sub-Lord shifts during NSE session")
    sunrise_time_str: Optional[str] = Field(None, description="Astronomical sunrise time for location")
    time_mode: str = Field("SUNRISE", description="Benchmark mode: SUNRISE or 09:00")
    city_name: str = Field("Ahmedabad", description="Location name")


class MarketWeekOutlookResponse(BaseModel):
    reference_date: str = Field(..., description="Reference date in YYYY-MM-DD")
    include_previous_week: bool = Field(..., description="Whether previous week (testing/audit) is included")
    include_next_week: bool = Field(..., description="Whether next week (projections) is included")
    time_mode: str = Field("SUNRISE", description="Benchmark time mode: SUNRISE or 09:00")
    city_name: str = Field("Ahmedabad", description="User preferred city")
    latitude: float = Field(23.0225, description="Latitude")
    longitude: float = Field(72.5714, description="Longitude")
    total_trading_days: int = Field(..., description="Total market trading days returned (5, 10, or 15)")
    days: List[MarketDayOutlookItem] = Field(..., description="List of trading days")

