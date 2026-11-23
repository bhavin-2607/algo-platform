import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import { X, Clock, AlertTriangle, Compass, ShieldAlert, Sparkles, Activity } from "lucide-react";

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

interface AstroPivotDrawerProps {
  open: boolean;
  onClose: () => void;
  signal: AstroMarketSignal | null;
}

export const AstroPivotDrawer: React.FC<AstroPivotDrawerProps> = ({ open, onClose, signal }) => {
  const [activeTab, setActiveTab] = useState<"TIMELINE" | "ASPECTS" | "EPHEMERIS">("TIMELINE");

  // Fetch today's intraday windows
  const { data: windowsData, isLoading: windowsLoading } = useQuery<IntradayAstroResponse>({
    queryKey: ["astro-intraday-windows"],
    queryFn: async () => {
      const res = await api.get("/v1/astro/intraday-windows");
      return res.data;
    },
    enabled: open,
    staleTime: 60000,
  });

  if (!open) return null;

  const isVol = signal?.volatility_alert;
  const isBullish = signal?.regime_bias === "BULLISH_TAILWIND";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(4px)",
        display: "flex",
        justifyContent: "flex-end",
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 620,
          height: "100%",
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "-8px 0 24px rgba(0, 0, 0, 0.5)",
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
            padding: "16px 20px",
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
                Lahiri Sidereal • KP Sub-Lord Vimshottari • Geometric Aspect Radar
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
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Real-time Summary Cards Strip */}
        {signal && (
          <div
            style={{
              padding: "12px 20px",
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 10,
              borderBottom: "1px solid var(--border)",
              background: "var(--bg)",
            }}
          >
            {/* Regime Bias */}
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 4,
                background: "var(--surface2)",
                border: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase" }}>
                Regime Bias
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
                  {signal.regime_bias === "HIGH_VOLATILITY_CAUTION"
                    ? "HIGH VOLATILITY"
                    : signal.regime_bias === "BULLISH_TAILWIND"
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
                background: "var(--surface2)",
                border: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase" }}>
                Net Aspect Sentiment
              </div>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 800,
                  marginTop: 4,
                  fontFamily: "monospace",
                  color:
                    signal.net_sentiment_score > 0
                      ? "var(--green)"
                      : signal.net_sentiment_score < 0
                      ? "var(--red)"
                      : "var(--text)",
                }}
              >
                {signal.net_sentiment_score > 0 ? `+${signal.net_sentiment_score}` : signal.net_sentiment_score}
                <span style={{ fontSize: 10, color: "var(--muted)", marginLeft: 6, fontWeight: 500 }}>
                  (H: {signal.hard_aspect_score} / S: {signal.soft_aspect_score})
                </span>
              </div>
            </div>

            {/* Current Moon Nakshatra & KP Sub */}
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 4,
                background: "var(--surface2)",
                border: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 10, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase" }}>
                Moon Transit
              </div>
              <div style={{ fontSize: 12, fontWeight: 800, marginTop: 4, color: "var(--text)" }}>
                {signal.moon_nakshatra}{" "}
                <span style={{ fontSize: 11, color: "var(--ba-cyan)", fontWeight: 700 }}>
                  / {signal.moon_kp_sub_lord} Sub
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
            }}
          >
            ASPECT RADAR & STRESS ({signal?.active_aspects.length || 0})
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
            }}
          >
            EPHEMERIS GRID ({signal?.planets.length || 0})
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
                }}
              >
                Intraday market windows track exact timestamps where the Moon changes Vedic Nakshatra (
                <strong style={{ color: "var(--red)" }}>HIGH</strong> cyclical weight) or KP Sub-Lord (
                <strong style={{ color: "var(--ba-cyan)" }}>MEDIUM</strong> benefic/malefic shift).
              </div>

              {windowsLoading ? (
                <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
                  Scanning today's NSE session (09:15 to 15:30 IST)...
                </div>
              ) : !windowsData || windowsData.windows.length === 0 ? (
                <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
                  No Moon Nakshatra or KP Sub-Lord boundary shifts detected during today's market hours. The Moon remains
                  stable in its current zone throughout 09:15–15:30 IST.
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
          {activeTab === "ASPECTS" && signal && (
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
                    Hard Aspects Stress: {signal.hard_aspect_score}
                  </span>
                  <span style={{ color: "var(--green)" }}>
                    Soft Aspects Harmony: {signal.soft_aspect_score}
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
                      width: `${Math.min(100, (signal.hard_aspect_score / (signal.hard_aspect_score + signal.soft_aspect_score || 1)) * 100)}%`,
                      background: "var(--red)",
                    }}
                  />
                  <div
                    style={{
                      flex: 1,
                      background: "var(--green)",
                    }}
                  />
                </div>
              </div>

              {/* Aspects Table */}
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "var(--font)" }}>
                  <thead>
                    <tr style={{ background: "var(--surface2)", borderBottom: "1px solid var(--border)", color: "var(--muted)", textAlign: "left" }}>
                      <th style={{ padding: "8px 10px" }}>PAIR</th>
                      <th style={{ padding: "8px 10px" }}>ASPECT</th>
                      <th style={{ padding: "8px 10px" }}>ANGLE</th>
                      <th style={{ padding: "8px 10px" }}>ORB</th>
                      <th style={{ padding: "8px 10px" }}>NATURE</th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>WEIGHT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {signal.active_aspects.map((asp, i) => (
                      <tr
                        key={i}
                        style={{
                          borderBottom: "1px solid rgba(255,255,255,0.04)",
                          background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                        }}
                      >
                        <td style={{ padding: "8px 10px", fontWeight: 700 }}>
                          {asp.body_a} - {asp.body_b}
                        </td>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: "var(--text)" }}>
                          {asp.aspect_type}
                        </td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace", color: "var(--muted)" }}>
                          {asp.separation_deg.toFixed(1)}°
                        </td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>
                          {asp.orb_deg.toFixed(2)}°
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 800,
                              padding: "2px 6px",
                              borderRadius: 3,
                              background: asp.is_hard ? "rgba(255,59,87,0.12)" : "rgba(0,230,118,0.12)",
                              color: asp.is_hard ? "var(--red)" : "var(--green)",
                            }}
                          >
                            {asp.is_hard ? "STRESS" : "HARMONY"}
                          </span>
                        </td>
                        <td
                          style={{
                            padding: "8px 10px",
                            textAlign: "right",
                            fontFamily: "monospace",
                            fontWeight: 700,
                            color: asp.is_hard ? "var(--red)" : "var(--green)",
                          }}
                        >
                          {asp.weight.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: EPHEMERIS GRID */}
          {activeTab === "EPHEMERIS" && signal && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "var(--font)" }}>
                <thead>
                  <tr style={{ background: "var(--surface2)", borderBottom: "1px solid var(--border)", color: "var(--muted)", textAlign: "left" }}>
                    <th style={{ padding: "8px 10px" }}>BODY</th>
                    <th style={{ padding: "8px 10px" }}>SIGN & DEGREE</th>
                    <th style={{ padding: "8px 10px" }}>NAKSHATRA</th>
                    <th style={{ padding: "8px 10px" }}>PADA</th>
                    <th style={{ padding: "8px 10px" }}>KP SUB-LORD</th>
                    <th style={{ padding: "8px 10px" }}>SPEED</th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {signal.planets.map((p, i) => (
                    <tr
                      key={p.name}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                        background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
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
          <span style={{ fontFamily: "monospace" }}>Auto-refresh: 5 min</span>
        </div>
      </div>
    </div>
  );
};
