from typing import List, Optional
from pydantic import BaseModel, Field


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
    regime_bias: str = Field(..., description="BULLISH_TAILWIND, HIGH_VOLATILITY_CAUTION, or NEUTRAL_RANGE")
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
