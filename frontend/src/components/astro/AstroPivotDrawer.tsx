import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import {
  X,
  Clock,
  AlertTriangle,
  Compass,
  ShieldAlert,
  Sparkles,
  Activity,
  ChevronLeft,
  ChevronRight,
  Calendar,
  Layers,
} from "lucide-react";
import {
  getAstroSettings,
  saveAstroSettings,
  AstroTimingSettings,
} from "@/utils/astroSettings";

export interface PlanetTelemetry {
  name: string;
  longitude: number;
  sign: string;
  sign_degree: number;
  sign_degree_str: string;
  nakshatra: string;
  nakshatra_lord: string;
  pada: number;
  kp_sub_lord: string;
  speed: number;
  is_retrograde: boolean;
  is_stationary: boolean;
}

export interface AspectDetail {
  body_a: string;
  body_b: string;
  aspect_type: string;
  target_deg: number;
  separation_deg: number;
  orb_deg: number;
  is_hard: boolean;
  weight: number;
  description: string;
}

export interface AstroMarketSignal {
  timestamp_iso: string;
  timestamp_utc: string;
  regime_bias: "BULLISH_TAILWIND" | "HIGH_VOLATILITY_CAUTION" | "NEUTRAL_RANGE" | string;
  volatility_alert: boolean;
  hard_aspect_score: number;
  soft_aspect_score: number;
  net_sentiment_score: number;
  moon_nakshatra: string;
  moon_kp_sub_lord: string;
  stationary_planets: string[];
  planets: PlanetTelemetry[];
  active_aspects: AspectDetail[];
  risk_multiplier: number;
}

export interface IntradayAstroWindow {
  timestamp: string;
  time_str: string;
  event_type: "MOON_NAKSHATRA_SHIFT" | "KP_SUB_LORD_SHIFT" | string;
  from_entity: string;
  to_entity: string;
  weight: "HIGH" | "MEDIUM" | "LOW" | string;
  description: string;
}

export interface IntradayAstroResponse {
  date: string;
  session_open: string;
  session_close: string;
  total_windows: number;
  windows: IntradayAstroWindow[];
}

export type WeekCategory = "PREVIOUS_WEEK" | "CURRENT_WEEK" | "NEXT_WEEK";

export interface MarketDayOutlookItem {
  date: string;
  day_name: string;
  day_of_week: number;
  week_category: WeekCategory;
  is_today: boolean;
  regime_bias: string;
  volatility_alert: boolean;
  hard_aspect_score: number;
  soft_aspect_score: number;
  net_sentiment_score: number;
  moon_nakshatra: string;
  moon_kp_sub_lord: string;
  total_shift_windows: number;
}

export interface MarketWeekOutlookResponse {
  reference_date: string;
  include_previous_week: boolean;
  include_next_week: boolean;
  total_trading_days: number;
  days: MarketDayOutlookItem[];
}

interface AstroPivotDrawerProps {
  open: boolean;
  onClose: () => void;
  signal: AstroMarketSignal | null;
}

export const AstroPivotDrawer: React.FC<AstroPivotDrawerProps> = ({ open, onClose, signal }) => {
  const [activeTab, setActiveTab] = useState<"TIMELINE" | "ASPECTS" | "EPHEMERIS">("TIMELINE");

  // Load persistent user settings
  const [settings, setSettings] = useState<AstroTimingSettings>(getAstroSettings);

  // Sync settings across components
  useEffect(() => {
    const handleSettingsUpdate = (e: Event) => {
      const customEvent = e as CustomEvent<AstroTimingSettings>;
      if (customEvent.detail) {
        setSettings(customEvent.detail);
      }
    };
    window.addEventListener("astro_settings_updated", handleSettingsUpdate);
    return () => window.removeEventListener("astro_settings_updated", handleSettingsUpdate);
  }, []);

  const todayDate = useMemo(() => {
    if (signal?.timestamp_iso) {
      return signal.timestamp_iso.slice(0, 10);
    }
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }, [signal]);

  const [selectedDate, setSelectedDate] = useState<string>(todayDate);

  // Sync selectedDate when drawer opens or todayDate updates
  useEffect(() => {
    if (open) {
      setSelectedDate(todayDate);
    }
  }, [open, todayDate]);

  // Query multi-week Monday-to-Friday market outlook
  const { data: weekData, isLoading: weekLoading } = useQuery<MarketWeekOutlookResponse>({
    queryKey: ["astro-market-week-outlook", settings.includePreviousWeek, settings.includeNextWeek, todayDate],
    queryFn: async () => {
      const res = await api.get(
        `/v1/astro/market-week-outlook?include_prev=${settings.includePreviousWeek}&include_next=${settings.includeNextWeek}&ref_date_str=${todayDate}`
      );
      return res.data;
    },
    enabled: open,
    staleTime: 60000,
  });

  // Query intraday shift windows for the selected trading day
  const { data: windowsData, isLoading: windowsLoading } = useQuery<IntradayAstroResponse>({
    queryKey: ["astro-intraday-windows", selectedDate],
    queryFn: async () => {
      const res = await api.get(`/v1/astro/intraday-windows?date_str=${selectedDate}`);
      return res.data;
    },
    enabled: open && !!selectedDate,
    staleTime: 60000,
  });

  // Query snapshot telemetry for selected trading day (midday 12:00 IST)
  const isSelectedToday = selectedDate === todayDate;
  const { data: selectedDaySnapshot, isLoading: snapshotLoading } = useQuery<AstroMarketSignal>({
    queryKey: ["astro-snapshot-day", selectedDate],
    queryFn: async () => {
      const res = await api.get(`/v1/astro/snapshot?timestamp_iso=${selectedDate}T12:00:00+05:30`);
      return res.data;
    },
    enabled: open && !isSelectedToday && !!selectedDate,
    staleTime: 60000,
  });

  const activeSignal: AstroMarketSignal | null = isSelectedToday && signal ? signal : selectedDaySnapshot ?? signal;

  const togglePreviousWeek = () => {
    const next = { ...settings, includePreviousWeek: !settings.includePreviousWeek };
    setSettings(next);
    saveAstroSettings(next);
  };

  const toggleNextWeek = () => {
    const next = { ...settings, includeNextWeek: !settings.includeNextWeek };
    setSettings(next);
    saveAstroSettings(next);
  };

  // Steppers logic through available trading days
  const tradingDays = weekData?.days ?? [];
  const currentDayIndex = tradingDays.findIndex((d) => d.date === selectedDate);

  const handlePrevDay = () => {
    if (currentDayIndex > 0) {
      setSelectedDate(tradingDays[currentDayIndex - 1].date);
    }
  };

  const handleNextDay = () => {
    if (currentDayIndex >= 0 && currentDayIndex < tradingDays.length - 1) {
      setSelectedDate(tradingDays[currentDayIndex + 1].date);
    }
  };

  if (!open) return null;

  const isVol = activeSignal?.volatility_alert;
  const isBullish = activeSignal?.regime_bias === "BULLISH_TAILWIND";

  // Group market days by week category
  const prevWeekDays = tradingDays.filter((d) => d.week_category === "PREVIOUS_WEEK");
  const currWeekDays = tradingDays.filter((d) => d.week_category === "CURRENT_WEEK");
  const nextWeekDays = tradingDays.filter((d) => d.week_category === "NEXT_WEEK");

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(0, 0, 0, 0.7)",
        backdropFilter: "blur(4px)",
        display: "flex",
        justifyContent: "flex-end",
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 680,
          height: "100%",
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "-12px 0 32px rgba(0, 0, 0, 0.6)",
          display: "flex",
          flexDirection: "column",
          color: "var(--text)",
          fontFamily: "var(--font)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Strip */}
        <div
          style={{
            padding: "14px 20px",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface2)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 6,
                background: isVol
                  ? "rgba(255,59,87,0.15)"
                  : isBullish
                  ? "rgba(0,230,118,0.15)"
                  : "rgba(8,182,222,0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: isVol ? "var(--red)" : isBullish ? "var(--green)" : "var(--ba-cyan)",
              }}
            >
              <Compass size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: 0.5 }}>
                  FINANCIAL ASTROLOGY & CYCLICAL TIMING
                </span>
                <span
                  style={{
                    fontSize: 9,
                    fontWeight: 700,
                    padding: "2px 6px",
                    borderRadius: 3,
                    background: "rgba(255, 255, 255, 0.08)",
                    color: "var(--muted)",
                  }}
                >
                  WATCH ONLY
                </span>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                Lahiri Sidereal • KP Sub-Lord Vimshottari • Monday-to-Friday Market Cycles
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            style={{
              padding: 6,
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: 4,
              color: "var(--muted)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Multi-Week Market Days Strip Header Controls */}
        <div
          style={{
            padding: "10px 20px",
            background: "var(--bg)",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 0.5, color: "var(--text)" }}>
                MARKET TRADING DAYS
              </span>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "1px 6px",
                  borderRadius: 3,
                  background:
                    selectedDate === todayDate
                      ? "rgba(0, 230, 118, 0.15)"
                      : selectedDate < todayDate
                      ? "rgba(255, 183, 3, 0.15)"
                      : "rgba(8, 182, 222, 0.15)",
                  color:
                    selectedDate === todayDate
                      ? "var(--green)"
                      : selectedDate < todayDate
                      ? "var(--yellow)"
                      : "var(--ba-cyan)",
                  border: `1px solid ${
                    selectedDate === todayDate
                      ? "rgba(0, 230, 118, 0.3)"
                      : selectedDate < todayDate
                      ? "rgba(255, 183, 3, 0.3)"
                      : "rgba(8, 182, 222, 0.3)"
                  }`,
                }}
              >
                {selectedDate === todayDate
                  ? "LIVE SESSION TODAY"
                  : selectedDate < todayDate
                  ? "HISTORICAL AUDIT"
                  : "CYCLICAL PROJECTION"}
              </span>
            </div>

            {/* Quick Toggle Buttons for Previous & Next Week */}
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <button
                type="button"
                onClick={togglePreviousWeek}
                title="Toggle Previous Week (Testing / Audit)"
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "3px 8px",
                  borderRadius: 3,
                  background: settings.includePreviousWeek ? "rgba(255, 183, 3, 0.15)" : "transparent",
                  color: settings.includePreviousWeek ? "var(--yellow)" : "var(--muted)",
                  border: `1px solid ${settings.includePreviousWeek ? "rgba(255, 183, 3, 0.4)" : "var(--border)"}`,
                  cursor: "pointer",
                }}
              >
                {settings.includePreviousWeek ? "AUDIT: ON" : "AUDIT: OFF"}
              </button>

              <button
                type="button"
                onClick={toggleNextWeek}
                title="Toggle Next Week (Forward Projections)"
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "3px 8px",
                  borderRadius: 3,
                  background: settings.includeNextWeek ? "rgba(8, 182, 222, 0.15)" : "transparent",
                  color: settings.includeNextWeek ? "var(--ba-cyan)" : "var(--muted)",
                  border: `1px solid ${settings.includeNextWeek ? "rgba(8, 182, 222, 0.4)" : "var(--border)"}`,
                  cursor: "pointer",
                }}
              >
                {settings.includeNextWeek ? "PROJ: ON" : "PROJ: OFF"}
              </button>

              <div style={{ height: 16, width: 1, background: "var(--border)", margin: "0 2px" }} />

              {/* Stepper Navigation */}
              <button
                type="button"
                onClick={handlePrevDay}
                disabled={currentDayIndex <= 0}
                style={{
                  padding: "3px 6px",
                  background: "transparent",
                  border: "1px solid var(--border)",
                  borderRadius: 3,
                  color: currentDayIndex > 0 ? "var(--text)" : "var(--muted)",
                  cursor: currentDayIndex > 0 ? "pointer" : "default",
                  display: "flex",
                  alignItems: "center",
                }}
                title="Previous Market Day"
              >
                <ChevronLeft size={13} />
              </button>

              <button
                type="button"
                onClick={() => setSelectedDate(todayDate)}
                style={{
                  fontSize: 10,
                  fontWeight: 800,
                  padding: "3px 8px",
                  borderRadius: 3,
                  background: selectedDate === todayDate ? "var(--ba-cyan)" : "var(--surface2)",
                  color: selectedDate === todayDate ? "#000" : "var(--text)",
                  border: `1px solid ${selectedDate === todayDate ? "var(--ba-cyan)" : "var(--border)"}`,
                  cursor: "pointer",
                }}
              >
                TODAY
              </button>

              <button
                type="button"
                onClick={handleNextDay}
                disabled={currentDayIndex < 0 || currentDayIndex >= tradingDays.length - 1}
                style={{
                  padding: "3px 6px",
                  background: "transparent",
                  border: "1px solid var(--border)",
                  borderRadius: 3,
                  color:
                    currentDayIndex >= 0 && currentDayIndex < tradingDays.length - 1
                      ? "var(--text)"
                      : "var(--muted)",
                  cursor:
                    currentDayIndex >= 0 && currentDayIndex < tradingDays.length - 1
                      ? "pointer"
                      : "default",
                  display: "flex",
                  alignItems: "center",
                }}
                title="Next Market Day"
              >
                <ChevronRight size={13} />
              </button>

              {/* Date Input for arbitrary jump */}
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => e.target.value && setSelectedDate(e.target.value)}
                style={{
                  background: "var(--surface2)",
                  border: "1px solid var(--border)",
                  borderRadius: 3,
                  padding: "2px 6px",
                  color: "var(--text)",
                  fontSize: 10,
                  cursor: "pointer",
                  height: 22,
                }}
              />
            </div>
          </div>

          {/* Horizontal Scrollable Monday-to-Friday Days Strip */}
          <div
            style={{
              display: "flex",
              alignItems: "stretch",
              gap: 8,
              overflowX: "auto",
              paddingBottom: 4,
            }}
          >
            {weekLoading && (
              <div style={{ fontSize: 11, color: "var(--muted)", padding: "10px 0" }}>
                Calculating market-days astrological cycles...
              </div>
            )}

            {/* Render Section: Previous Week (Audit) */}
            {settings.includePreviousWeek && prevWeekDays.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  padding: "6px 8px",
                  background: "rgba(255, 183, 3, 0.04)",
                  borderRadius: 4,
                  border: "1px dashed rgba(255, 183, 3, 0.25)",
                }}
              >
                <div style={{ fontSize: 9, fontWeight: 800, color: "var(--yellow)", letterSpacing: 0.5 }}>
                  PREVIOUS WEEK (TESTING / AUDIT)
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {prevWeekDays.map((day) => renderMarketDayChip(day, selectedDate, setSelectedDate))}
                </div>
              </div>
            )}

            {/* Render Section: Current Week */}
            {currWeekDays.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  padding: "6px 8px",
                  background: "rgba(8, 182, 222, 0.04)",
                  borderRadius: 4,
                  border: "1px solid rgba(8, 182, 222, 0.25)",
                }}
              >
                <div style={{ fontSize: 9, fontWeight: 800, color: "var(--ba-cyan)", letterSpacing: 0.5 }}>
                  CURRENT WEEK (ACTIVE)
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {currWeekDays.map((day) => renderMarketDayChip(day, selectedDate, setSelectedDate))}
                </div>
              </div>
            )}

            {/* Render Section: Next Week (Projected) */}
            {settings.includeNextWeek && nextWeekDays.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  padding: "6px 8px",
                  background: "rgba(168, 85, 247, 0.04)",
                  borderRadius: 4,
                  border: "1px dashed rgba(168, 85, 247, 0.25)",
                }}
              >
                <div style={{ fontSize: 9, fontWeight: 800, color: "#c084fc", letterSpacing: 0.5 }}>
                  NEXT WEEK (PROJECTED TIMING)
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {nextWeekDays.map((day) => renderMarketDayChip(day, selectedDate, setSelectedDate))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Real-time Summary Cards Strip for Selected Trading Day */}
        {activeSignal && (
          <div
            style={{
              padding: "12px 20px",
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 10,
              borderBottom: "1px solid var(--border)",
              background: "var(--surface2)",
            }}
          >
            {/* Regime Bias */}
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 4,
                background: "var(--surface)",
                border: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase" }}>
                Regime Bias ({selectedDate})
              </div>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 800,
                  marginTop: 4,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  color: isVol ? "var(--red)" : isBullish ? "var(--green)" : "var(--text)",
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: isVol ? "var(--red)" : isBullish ? "var(--green)" : "var(--muted)",
                    boxShadow: isVol
                      ? "0 0 6px var(--red)"
                      : isBullish
                      ? "0 0 6px var(--green)"
                      : "none",
                  }}
                />
                <span>
                  {activeSignal.regime_bias === "HIGH_VOLATILITY_CAUTION"
                    ? "HIGH VOLATILITY"
                    : activeSignal.regime_bias === "BULLISH_TAILWIND"
                    ? "BULLISH TAILWIND"
                    : "NEUTRAL RANGE"}
                </span>
              </div>
            </div>

            {/* Net Sentiment Score */}
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 4,
                background: "var(--surface)",
                border: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase" }}>
                Net Aspect Stress / Sentiment
              </div>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 800,
                  marginTop: 4,
                  fontFamily: "monospace",
                  color:
                    activeSignal.net_sentiment_score > 0
                      ? "var(--green)"
                      : activeSignal.net_sentiment_score < 0
                      ? "var(--red)"
                      : "var(--text)",
                }}
              >
                {activeSignal.net_sentiment_score > 0
                  ? `+${activeSignal.net_sentiment_score}`
                  : activeSignal.net_sentiment_score}
                <span style={{ fontSize: 10, color: "var(--muted)", marginLeft: 6, fontWeight: 500 }}>
                  (H: {activeSignal.hard_aspect_score} / S: {activeSignal.soft_aspect_score})
                </span>
              </div>
            </div>

            {/* Moon Nakshatra & KP Sub */}
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 4,
                background: "var(--surface)",
                border: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase" }}>
                Moon Transit (Midday)
              </div>
              <div style={{ fontSize: 12, fontWeight: 800, marginTop: 4, color: "var(--text)" }}>
                {activeSignal.moon_nakshatra}{" "}
                <span style={{ fontSize: 11, color: "var(--ba-cyan)", fontWeight: 700 }}>
                  / {activeSignal.moon_kp_sub_lord} Sub
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div
          style={{
            display: "flex",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface)",
            padding: "0 20px",
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab("TIMELINE")}
            style={{
              padding: "10px 14px",
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: 0.5,
              color: activeTab === "TIMELINE" ? "var(--ba-cyan)" : "var(--muted)",
              borderBottom: `2px solid ${activeTab === "TIMELINE" ? "var(--ba-cyan)" : "transparent"}`,
              background: "transparent",
              cursor: "pointer",
            }}
          >
            NSE SESSION TIMELINE (09:15 - 15:30)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("ASPECTS")}
            style={{
              padding: "10px 14px",
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: 0.5,
              color: activeTab === "ASPECTS" ? "var(--ba-cyan)" : "var(--muted)",
              borderBottom: `2px solid ${activeTab === "ASPECTS" ? "var(--ba-cyan)" : "transparent"}`,
              background: "transparent",
              cursor: "pointer",
            }}
          >
            ASPECT RADAR & STRESS ({activeSignal?.active_aspects.length || 0})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("EPHEMERIS")}
            style={{
              padding: "10px 14px",
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: 0.5,
              color: activeTab === "EPHEMERIS" ? "var(--ba-cyan)" : "var(--muted)",
              borderBottom: `2px solid ${activeTab === "EPHEMERIS" ? "var(--ba-cyan)" : "transparent"}`,
              background: "transparent",
              cursor: "pointer",
            }}
          >
            EPHEMERIS GRID ({activeSignal?.planets.length || 0})
          </button>
        </div>

        {/* Tab Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {/* TAB 1: NSE SESSION TIMELINE */}
          {activeTab === "TIMELINE" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div
                style={{
                  padding: "10px 14px",
                  background: "var(--surface2)",
                  borderRadius: 4,
                  border: "1px solid var(--border)",
                  fontSize: 11,
                  color: "var(--muted)",
                  lineHeight: 1.5,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span>
                  Tracking exact timestamps during NSE hours for{" "}
                  <strong style={{ color: "var(--text)" }}>{selectedDate}</strong> where the Moon changes Vedic
                  Nakshatra (<strong style={{ color: "var(--red)" }}>HIGH</strong> cyclical impact) or KP Sub-Lord (
                  <strong style={{ color: "var(--ba-cyan)" }}>MEDIUM</strong> benefic/malefic shift).
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "var(--ba-cyan)",
                    whiteSpace: "nowrap",
                    marginLeft: 12,
                  }}
                >
                  {windowsData?.total_windows ?? 0} SHIFTS
                </span>
              </div>

              {windowsLoading ? (
                <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
                  Scanning session (09:15 to 15:30 IST) for {selectedDate}...
                </div>
              ) : !windowsData || windowsData.windows.length === 0 ? (
                <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
                  No Moon Nakshatra or KP Sub-Lord boundary shifts detected during {selectedDate} market hours. The Moon
                  remains stable in its current zone throughout 09:15–15:30 IST.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {windowsData.windows.map((win, idx) => {
                    const isHigh = win.weight === "HIGH";
                    const isMed = win.weight === "MEDIUM";

                    const badgeColor = isHigh ? "var(--red)" : isMed ? "var(--yellow)" : "var(--muted)";
                    const badgeBg = isHigh
                      ? "rgba(255,59,87,0.12)"
                      : isMed
                      ? "rgba(255,183,3,0.12)"
                      : "rgba(255,255,255,0.06)";

                    return (
                      <div
                        key={idx}
                        style={{
                          padding: "12px 14px",
                          borderRadius: 4,
                          background: "var(--surface2)",
                          border: `1px solid ${isHigh ? "rgba(255,59,87,0.35)" : "var(--border)"}`,
                          display: "flex",
                          flexDirection: "column",
                          gap: 6,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span
                              style={{
                                fontFamily: "monospace",
                                fontSize: 13,
                                fontWeight: 800,
                                color: "var(--text)",
                              }}
                            >
                              {win.time_str}
                            </span>
                            <span
                              style={{
                                fontSize: 9,
                                fontWeight: 800,
                                padding: "2px 6px",
                                borderRadius: 3,
                                background: badgeBg,
                                color: badgeColor,
                                border: `1px solid ${badgeColor}`,
                              }}
                            >
                              {win.weight} IMPACT
                            </span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
                              {win.event_type === "MOON_NAKSHATRA_SHIFT" ? "Nakshatra Shift" : "KP Sub-Lord Shift"}
                            </span>
                          </div>

                          <div style={{ fontSize: 11, fontFamily: "monospace", color: "var(--muted)" }}>
                            {win.from_entity} → <strong style={{ color: "var(--text)" }}>{win.to_entity}</strong>
                          </div>
                        </div>

                        <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.4 }}>
                          {win.description}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: ASPECT RADAR & STRESS */}
          {activeTab === "ASPECTS" && activeSignal && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* Stress vs Harmony Visual Bar */}
              <div
                style={{
                  padding: "12px 16px",
                  borderRadius: 4,
                  background: "var(--surface2)",
                  border: "1px solid var(--border)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700 }}>
                  <span style={{ color: "var(--red)" }}>
                    Hard Aspects Stress: {activeSignal.hard_aspect_score}
                  </span>
                  <span style={{ color: "var(--green)" }}>
                    Soft Aspects Harmony: {activeSignal.soft_aspect_score}
                  </span>
                </div>

                <div
                  style={{
                    height: 8,
                    background: "rgba(255, 255, 255, 0.08)",
                    borderRadius: 4,
                    overflow: "hidden",
                    display: "flex",
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(
                        100,
                        (activeSignal.hard_aspect_score /
                          (activeSignal.hard_aspect_score + activeSignal.soft_aspect_score || 1)) *
                          100
                      )}%`,
                      background: "var(--red)",
                    }}
                  />
                  <div
                    style={{
                      width: `${Math.min(
                        100,
                        (activeSignal.soft_aspect_score /
                          (activeSignal.hard_aspect_score + activeSignal.soft_aspect_score || 1)) *
                          100
                      )}%`,
                      background: "var(--green)",
                    }}
                  />
                </div>
              </div>

              {/* Aspects List */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {activeSignal.active_aspects.length === 0 ? (
                  <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
                    No major geometric aspects active within strict orbs on {selectedDate}.
                  </div>
                ) : (
                  activeSignal.active_aspects.map((asp, idx) => {
                    const isHard = asp.is_hard;
                    const aspectColor = isHard ? "var(--red)" : "var(--green)";

                    return (
                      <div
                        key={idx}
                        style={{
                          padding: "10px 14px",
                          borderRadius: 4,
                          background: "var(--surface2)",
                          border: "1px solid var(--border)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: aspectColor,
                            }}
                          />
                          <div>
                            <div style={{ fontSize: 12, fontWeight: 800, color: "var(--text)" }}>
                              {asp.body_a}{" "}
                              <span style={{ color: aspectColor, margin: "0 4px" }}>{asp.aspect_type}</span>{" "}
                              {asp.body_b}
                            </div>
                            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                              {asp.description}
                            </div>
                          </div>
                        </div>

                        <div style={{ textAlign: "right", fontFamily: "monospace" }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
                            Orb: {asp.orb_deg}°
                          </div>
                          <div style={{ fontSize: 10, color: aspectColor }}>
                            Weight: {asp.weight.toFixed(2)}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* TAB 3: PLANETARY EPHEMERIS GRID */}
          {activeTab === "EPHEMERIS" && activeSignal && (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 11,
                  textAlign: "left",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--border)",
                      color: "var(--muted)",
                      fontSize: 10,
                      textTransform: "uppercase",
                    }}
                  >
                    <th style={{ padding: "8px 10px" }}>Body</th>
                    <th style={{ padding: "8px 10px" }}>Sidereal Sign</th>
                    <th style={{ padding: "8px 10px" }}>Nakshatra</th>
                    <th style={{ padding: "8px 10px" }}>Pada</th>
                    <th style={{ padding: "8px 10px" }}>KP Sub-Lord</th>
                    <th style={{ padding: "8px 10px" }}>Speed</th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>Motion</th>
                  </tr>
                </thead>
                <tbody>
                  {activeSignal.planets.map((p, idx) => (
                    <tr
                      key={idx}
                      style={{
                        borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                        background: idx % 2 === 0 ? "transparent" : "rgba(255, 255, 255, 0.015)",
                      }}
                    >
                      <td style={{ padding: "8px 10px", fontWeight: 800, color: "var(--text)" }}>
                        {p.name}
                      </td>
                      <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>
                        <span style={{ fontWeight: 700, color: "var(--ba-cyan)" }}>{p.sign}</span>{" "}
                        <span style={{ color: "var(--muted)", fontSize: 10 }}>{p.sign_degree_str}</span>
                      </td>
                      <td style={{ padding: "8px 10px", fontWeight: 700 }}>
                        {p.nakshatra}{" "}
                        <span style={{ fontSize: 9, color: "var(--muted)" }}>({p.nakshatra_lord})</span>
                      </td>
                      <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>
                        P{p.pada}
                      </td>
                      <td style={{ padding: "8px 10px", fontWeight: 700, color: "var(--ba-amber)" }}>
                        {p.kp_sub_lord}
                      </td>
                      <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>
                        {p.speed > 0 ? `+${p.speed.toFixed(2)}` : p.speed.toFixed(2)}°/d
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>
                        {p.is_stationary ? (
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 800,
                              padding: "2px 5px",
                              borderRadius: 3,
                              background: "rgba(255,59,87,0.2)",
                              color: "var(--red)",
                            }}
                          >
                            STATIONARY
                          </span>
                        ) : p.is_retrograde ? (
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 800,
                              padding: "2px 5px",
                              borderRadius: 3,
                              background: "rgba(255,183,3,0.15)",
                              color: "var(--yellow)",
                            }}
                          >
                            RETRO
                          </span>
                        ) : (
                          <span style={{ fontSize: 9, color: "var(--muted)" }}>DIRECT</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer Note */}
        <div
          style={{
            padding: "10px 20px",
            borderTop: "1px solid var(--border)",
            background: "var(--surface2)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: 10,
            color: "var(--muted)",
          }}
        >
          <span>Swiss Ephemeris Moshier Analytical Model (Lahiri Sidereal Mode)</span>
          <span style={{ fontFamily: "monospace" }}>Selected: {selectedDate} (Midday 12:00 IST)</span>
        </div>
      </div>
    </div>
  );
};

// Helper component for rendering individual Monday-to-Friday market day chips
function renderMarketDayChip(
  day: MarketDayOutlookItem,
  selectedDate: string,
  onSelect: (date: string) => void
) {
  const isSelected = selectedDate === day.date;
  const isVol = day.volatility_alert;
  const isBull = day.regime_bias === "BULLISH_TAILWIND";

  const dotColor = isVol ? "var(--red)" : isBull ? "var(--green)" : "var(--muted)";
  const formattedDate = day.date.slice(5); // MM-DD

  return (
    <button
      key={day.date}
      type="button"
      onClick={() => onSelect(day.date)}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "6px 8px",
        minWidth: 70,
        borderRadius: 4,
        background: isSelected ? "var(--surface2)" : "var(--surface)",
        border: isSelected
          ? "1px solid var(--ba-cyan)"
          : day.is_today
          ? "1px solid rgba(0, 230, 118, 0.4)"
          : "1px solid var(--border)",
        boxShadow: isSelected ? "0 0 8px rgba(8, 182, 222, 0.25)" : "none",
        cursor: "pointer",
        position: "relative",
      }}
    >
      {day.is_today && (
        <span
          style={{
            position: "absolute",
            top: -6,
            right: 4,
            fontSize: 7,
            fontWeight: 800,
            padding: "1px 4px",
            borderRadius: 2,
            background: "var(--green)",
            color: "#000",
          }}
        >
          TODAY
        </span>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: "50%",
            background: dotColor,
          }}
        />
        <span
          style={{
            fontSize: 10,
            fontWeight: isSelected ? 800 : 700,
            color: isSelected ? "var(--ba-cyan)" : "var(--text)",
          }}
        >
          {day.day_name} {formattedDate}
        </span>
      </div>

      <div
        style={{
          fontSize: 9,
          fontWeight: 700,
          fontFamily: "monospace",
          marginTop: 2,
          color:
            day.net_sentiment_score > 0
              ? "var(--green)"
              : day.net_sentiment_score < 0
              ? "var(--red)"
              : "var(--muted)",
        }}
      >
        {day.net_sentiment_score > 0 ? `+${day.net_sentiment_score}` : day.net_sentiment_score}
      </div>

      <div style={{ fontSize: 8, color: "var(--muted)", marginTop: 1 }}>
        {day.total_shift_windows} shifts
      </div>
    </button>
  );
}
