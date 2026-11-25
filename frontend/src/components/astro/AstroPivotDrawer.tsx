import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import {
  X,
  Clock,
  Compass,
  Moon,
  Calendar,
  Layers,
  ChevronRight,
  Info,
  Sparkles,
  ArrowRight,
  BookOpen,
} from "lucide-react";

export interface MoonTransitCurrent {
  rashi: string;
  rashi_sanskrit: string;
  rashi_lord: string;
  degree: number;
  degree_dms: string;
  total_longitude: number;
  nakshatra: string;
  nakshatra_number: number;
  nakshatra_lord: string;
  pada: number;
  kp_sub_lord: string;
  daily_speed_deg: number;
  daily_speed_dms: string;
  rashi_progress_pct: number;
  rashi_ingress_ist: string;
  rashi_egress_ist: string;
  rashi_remaining_hours: number;
  rashi_remaining_str: string;
  next_rashi: string;
  next_rashi_sanskrit: string;
  next_rashi_lord: string;
  nakshatra_progress_pct: number;
  nakshatra_ingress_ist: string;
  nakshatra_egress_ist: string;
  nakshatra_remaining_hours: number;
  nakshatra_remaining_str: string;
  next_nakshatra: string;
  next_nakshatra_lord: string;
}

export interface MoonTransitScheduleItem {
  rashi: string;
  rashi_sanskrit: string;
  rashi_lord: string;
  ingress_ist: string;
  egress_ist: string;
  duration_hours: number;
}

export interface MoonTransitSnapshot {
  calculated_at_ist: string;
  current: MoonTransitCurrent;
  upcoming_schedule: MoonTransitScheduleItem[];
}

// Backwards compatibility types for legacy consumers
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
  speed_str?: string;
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
  reference_time_label?: string;
  sunrise_time_iso?: string;
  city_name?: string;
  latitude?: number;
  longitude?: number;
  regime_bias: string;
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
  moon_transit?: MoonTransitCurrent;
}

export interface IntradayAstroWindow {
  timestamp: string;
  time_str: string;
  event_type: string;
  from_entity: string;
  to_entity: string;
  weight: string;
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
  sunrise_time_str?: string;
  time_mode?: string;
}

export interface MarketWeekOutlookResponse {
  reference_date: string;
  include_previous_week: boolean;
  include_next_week: boolean;
  time_mode: string;
  total_trading_days: number;
  days: MarketDayOutlookItem[];
}

export interface AstroPivotDrawerProps {
  open: boolean;
  onClose: () => void;
  signal?: AstroMarketSignal | null;
}

export const AstroPivotDrawer: React.FC<AstroPivotDrawerProps> = ({ open, onClose, signal }) => {
  const [activeTab, setActiveTab] = useState<"TRANSIT" | "SCHEDULE" | "RULES">("TRANSIT");

  const { data: moonSnapshot, isLoading, refetch } = useQuery<MoonTransitSnapshot>({
    queryKey: ["moon-transit-telemetry"],
    queryFn: async () => {
      const res = await api.get("/v1/astro/moon-transit");
      return res.data;
    },
    enabled: open,
    refetchInterval: open ? 30000 : false,
    staleTime: 15000,
  });

  if (!open) return null;

  const current = moonSnapshot?.current || signal?.moon_transit;
  const schedule = moonSnapshot?.upcoming_schedule || [];
  const calculatedAt = moonSnapshot?.calculated_at_ist || (signal ? signal.timestamp_iso : "Live");

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        justifyContent: "flex-end",
        backgroundColor: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(3px)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 620,
          height: "100%",
          backgroundColor: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "-8px 0 24px rgba(0, 0, 0, 0.45)",
          display: "flex",
          flexDirection: "column",
          color: "var(--text)",
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--surface2)",
            position: "sticky",
            top: 0,
            zIndex: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                background: "rgba(0, 229, 255, 0.12)",
                border: "1px solid rgba(0, 229, 255, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--ba-cyan)",
              }}
            >
              <Moon size={18} />
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: 0.3, display: "flex", alignItems: "center", gap: 8 }}>
                <span>Moon Transit Watch</span>
                <span
                  style={{
                    fontSize: 9,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    padding: "2px 6px",
                    borderRadius: 4,
                    background: "rgba(0, 230, 118, 0.15)",
                    color: "var(--green)",
                    border: "1px solid rgba(0, 230, 118, 0.3)",
                  }}
                >
                  LIVE
                </span>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                Vedic Lunar Telemetry & Sidereal Ingress Tracker • Swiss Ephemeris
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                background: "transparent",
                border: "none",
                color: "var(--muted)",
                cursor: "pointer",
                padding: 6,
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              title="Close drawer"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div
          style={{
            display: "flex",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface)",
            padding: "0 16px",
          }}
        >
          <button
            onClick={() => setActiveTab("TRANSIT")}
            style={{
              flex: 1,
              padding: "10px 12px",
              fontSize: 12,
              fontWeight: 600,
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "TRANSIT" ? "2px solid var(--ba-cyan)" : "2px solid transparent",
              color: activeTab === "TRANSIT" ? "var(--ba-cyan)" : "var(--muted)",
              cursor: "pointer",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
            }}
          >
            <Compass size={14} />
            <span>Live Telemetry</span>
          </button>
          <button
            onClick={() => setActiveTab("SCHEDULE")}
            style={{
              flex: 1,
              padding: "10px 12px",
              fontSize: 12,
              fontWeight: 600,
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "SCHEDULE" ? "2px solid var(--ba-cyan)" : "2px solid transparent",
              color: activeTab === "SCHEDULE" ? "var(--ba-cyan)" : "var(--muted)",
              cursor: "pointer",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
            }}
          >
            <Calendar size={14} />
            <span>Transit Schedule (7-Day)</span>
          </button>
          <button
            onClick={() => setActiveTab("RULES")}
            style={{
              flex: 1,
              padding: "10px 12px",
              fontSize: 12,
              fontWeight: 600,
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "RULES" ? "2px solid var(--ba-cyan)" : "2px solid transparent",
              color: activeTab === "RULES" ? "var(--ba-cyan)" : "var(--muted)",
              cursor: "pointer",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
            }}
          >
            <BookOpen size={14} />
            <span>Custom Rules</span>
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
          {isLoading && !current && (
            <div style={{ textAlign: "center", padding: "40px 0", color: "var(--muted)", fontSize: 13 }}>
              Calculating high-precision Swiss Ephemeris lunar telemetry...
            </div>
          )}

          {current && activeTab === "TRANSIT" && (
            <>
              {/* Hero Status Card */}
              <div
                style={{
                  background: "linear-gradient(135deg, rgba(0, 229, 255, 0.08) 0%, rgba(124, 77, 255, 0.08) 100%)",
                  border: "1px solid rgba(0, 229, 255, 0.25)",
                  borderRadius: 10,
                  padding: 16,
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.8, color: "var(--muted)" }}>
                      Active Moon Sidereal Position
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "var(--text)", marginTop: 2, display: "flex", alignItems: "center", gap: 8 }}>
                      <span>{current.rashi}</span>
                      <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ba-cyan)" }}>({current.rashi_sanskrit})</span>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Exact Degree in Sign
                    </div>
                    <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "monospace", color: "var(--green)" }}>
                      {current.degree_dms}
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: 8,
                    marginTop: 4,
                  }}
                >
                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.25)",
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>Rashi Lord</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 2 }}>
                      {current.rashi_lord}
                    </div>
                  </div>

                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.25)",
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>Nakshatra</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 2 }}>
                      {current.nakshatra} (P{current.pada})
                    </div>
                  </div>

                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.25)",
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>Nakshatra Lord</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 2 }}>
                      {current.nakshatra_lord}
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.25)",
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>KP Sub-Lord</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 2 }}>
                      {current.kp_sub_lord}
                    </div>
                  </div>

                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.25)",
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>Daily Speed</div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginTop: 2 }}>
                      {current.daily_speed_dms}/d
                    </div>
                  </div>

                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.25)",
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>Total Longitude</div>
                    <div style={{ fontSize: 12, fontWeight: 600, fontFamily: "monospace", color: "var(--text)", marginTop: 2 }}>
                      {current.total_longitude}°
                    </div>
                  </div>
                </div>
              </div>

              {/* Rashi Transit Progress Card */}
              <div
                style={{
                  background: "var(--surface2)",
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  padding: 16,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <Clock size={14} style={{ color: "var(--ba-cyan)" }} />
                    <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Sign Transit Progress ({current.rashi})
                    </span>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "var(--ba-cyan)", fontFamily: "monospace" }}>
                    {current.rashi_progress_pct}%
                  </span>
                </div>

                {/* Progress Bar */}
                <div
                  style={{
                    width: "100%",
                    height: 8,
                    borderRadius: 4,
                    background: "rgba(255, 255, 255, 0.08)",
                    overflow: "hidden",
                    position: "relative",
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(100, Math.max(0, current.rashi_progress_pct))}%`,
                      height: "100%",
                      background: "linear-gradient(90deg, var(--ba-cyan) 0%, var(--green) 100%)",
                      borderRadius: 4,
                      transition: "width 0.3s ease",
                    }}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)" }}>
                  <div>
                    <span style={{ color: "var(--text)", fontWeight: 600 }}>Ingress: </span>
                    {current.rashi_ingress_ist}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{ color: "var(--text)", fontWeight: 600 }}>Egress: </span>
                    {current.rashi_egress_ist}
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    paddingTop: 8,
                    borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: "var(--muted)" }}>Remaining in {current.rashi}:</span>
                  <span
                    style={{
                      fontWeight: 800,
                      color: "var(--ba-yellow, #ffb300)",
                      fontFamily: "monospace",
                      background: "rgba(255, 179, 0, 0.1)",
                      padding: "2px 8px",
                      borderRadius: 4,
                      border: "1px solid rgba(255, 179, 0, 0.25)",
                    }}
                  >
                    {current.rashi_remaining_str}
                  </span>
                </div>
              </div>

              {/* Nakshatra Transit Progress Card */}
              <div
                style={{
                  background: "var(--surface2)",
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  padding: 16,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <Layers size={14} style={{ color: "var(--purple, #b388ff)" }} />
                    <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Nakshatra Progress ({current.nakshatra} #{current.nakshatra_number})
                    </span>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "var(--purple, #b388ff)", fontFamily: "monospace" }}>
                    {current.nakshatra_progress_pct}%
                  </span>
                </div>

                {/* Progress Bar */}
                <div
                  style={{
                    width: "100%",
                    height: 8,
                    borderRadius: 4,
                    background: "rgba(255, 255, 255, 0.08)",
                    overflow: "hidden",
                    position: "relative",
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(100, Math.max(0, current.nakshatra_progress_pct))}%`,
                      height: "100%",
                      background: "linear-gradient(90deg, #7c4dff 0%, #b388ff 100%)",
                      borderRadius: 4,
                      transition: "width 0.3s ease",
                    }}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)" }}>
                  <div>
                    <span style={{ color: "var(--text)", fontWeight: 600 }}>Entered: </span>
                    {current.nakshatra_ingress_ist}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{ color: "var(--text)", fontWeight: 600 }}>Exits: </span>
                    {current.nakshatra_egress_ist}
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    paddingTop: 8,
                    borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: "var(--muted)" }}>Remaining in {current.nakshatra}:</span>
                  <span
                    style={{
                      fontWeight: 800,
                      color: "var(--purple, #b388ff)",
                      fontFamily: "monospace",
                      background: "rgba(179, 136, 255, 0.1)",
                      padding: "2px 8px",
                      borderRadius: 4,
                      border: "1px solid rgba(179, 136, 255, 0.25)",
                    }}
                  >
                    {current.nakshatra_remaining_str}
                  </span>
                </div>
              </div>

              {/* Next Ingress Highlight Card */}
              <div
                style={{
                  background: "rgba(0, 229, 255, 0.04)",
                  border: "1px solid rgba(0, 229, 255, 0.2)",
                  borderRadius: 10,
                  padding: 14,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
                    Next Ingress Target
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", marginTop: 2, display: "flex", alignItems: "center", gap: 6 }}>
                    <span>{current.next_rashi} ({current.next_rashi_sanskrit})</span>
                    <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500 }}>• Lord: {current.next_rashi_lord}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                    Next Nakshatra: <strong style={{ color: "var(--text)" }}>{current.next_nakshatra}</strong> (Lord: {current.next_nakshatra_lord})
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>Ingress IST</div>
                  <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "monospace", color: "var(--ba-cyan)", marginTop: 2 }}>
                    {current.rashi_egress_ist}
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Upcoming Schedule Tab */}
          {activeTab === "SCHEDULE" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
                Chronological timeline of the Moon's upcoming sign transits calculated via high-precision Swiss Ephemeris root finding.
              </div>

              <div
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  overflow: "hidden",
                  background: "var(--surface2)",
                }}
              >
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1.2fr 1fr 1.6fr 1.6fr 0.8fr",
                    padding: "8px 12px",
                    background: "rgba(0, 0, 0, 0.35)",
                    borderBottom: "1px solid var(--border)",
                    fontSize: 11,
                    fontWeight: 700,
                    color: "var(--muted)",
                    textTransform: "uppercase",
                  }}
                >
                  <div>Rashi (Sign)</div>
                  <div>Lord</div>
                  <div>Ingress (IST)</div>
                  <div>Egress (IST)</div>
                  <div style={{ textAlign: "right" }}>Duration</div>
                </div>

                {schedule.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1.2fr 1fr 1.6fr 1.6fr 0.8fr",
                      padding: "10px 12px",
                      borderBottom: idx < schedule.length - 1 ? "1px solid rgba(255, 255, 255, 0.05)" : "none",
                      fontSize: 12,
                      alignItems: "center",
                      background: idx === 0 ? "rgba(0, 229, 255, 0.04)" : "transparent",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, color: "var(--text)" }}>{item.rashi}</div>
                      <div style={{ fontSize: 10, color: "var(--muted)" }}>{item.rashi_sanskrit}</div>
                    </div>
                    <div style={{ color: "var(--ba-cyan)", fontWeight: 600 }}>{item.rashi_lord}</div>
                    <div style={{ fontSize: 11, fontFamily: "monospace", color: "var(--text)" }}>{item.ingress_ist}</div>
                    <div style={{ fontSize: 11, fontFamily: "monospace", color: "var(--text)" }}>{item.egress_ist}</div>
                    <div style={{ textAlign: "right", fontFamily: "monospace", fontSize: 11, color: "var(--muted)" }}>
                      {item.duration_hours}h
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* User Custom Extension & Domain Rules Tab */}
          {activeTab === "RULES" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div
                style={{
                  background: "rgba(0, 229, 255, 0.06)",
                  border: "1px solid rgba(0, 229, 255, 0.25)",
                  borderRadius: 8,
                  padding: 14,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ba-cyan)", fontWeight: 700, fontSize: 13 }}>
                  <Sparkles size={16} />
                  <span>User Custom Rules & Lunar Formula Extension</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--text)", lineHeight: 1.5 }}>
                  This section is reserved for your specialized trading rules, Gann lunar price-time angles, Nakshatra market biases, and Lunar Day (Tithi) indicators.
                </div>
              </div>

              <div
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: 14,
                  background: "var(--surface2)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", color: "var(--muted)", letterSpacing: 0.5 }}>
                  Extension Slots (Awaiting Information)
                </div>

                <div
                  style={{
                    background: "rgba(0, 0, 0, 0.25)",
                    border: "1px dashed var(--border)",
                    borderRadius: 6,
                    padding: 12,
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                    1. Gann Lunar Degree & Angular Harmonics
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                    Define cardinal / fixed cross angles (0°, 90°, 180°, 270°) or harmonic divisions from Moon entry.
                  </div>
                </div>

                <div
                  style={{
                    background: "rgba(0, 0, 0, 0.25)",
                    border: "1px dashed var(--border)",
                    borderRadius: 6,
                    padding: 12,
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                    2. Moon-Gandanta Junction Sensitivity
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                    Monitor the critical 0° Water-Fire transitions (Cancer-Leo, Scorpio-Sagittarius, Pisces-Aries) for extreme volatility pauses.
                  </div>
                </div>

                <div
                  style={{
                    background: "rgba(0, 0, 0, 0.25)",
                    border: "1px dashed var(--border)",
                    borderRadius: 6,
                    padding: 12,
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                    3. Nakshatra & Pada Market Directional Rules
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                    Configure specific trading bias (e.g. Rohini Bullish, Bharani Rangebound) or instrument-specific filters.
                  </div>
                </div>

                <div
                  style={{
                    background: "rgba(0, 0, 0, 0.25)",
                    border: "1px dashed var(--border)",
                    borderRadius: 6,
                    padding: 12,
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                    4. Vedic Tithi & Lunar Phase Indicators
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                    Track Shukla / Krishna Paksha and Tithi progression relative to the Sun.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Footer Timestamp */}
          <div
            style={{
              paddingTop: 12,
              borderTop: "1px solid var(--border)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 11,
              color: "var(--muted)",
            }}
          >
            <span>Calculated at: {calculatedAt}</span>
            <span style={{ color: "var(--ba-cyan)", fontWeight: 600 }}>Lahiri Sidereal Mode</span>
          </div>
        </div>
      </div>
    </div>
  );
};
