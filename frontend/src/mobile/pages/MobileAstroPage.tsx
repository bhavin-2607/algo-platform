import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import {
  Moon,
  Compass,
  Calendar,
  Layers,
  Clock,
  Sparkles,
  BookOpen,
} from "lucide-react";
import {
  MoonTransitSnapshot,
} from "@/components/astro/AstroPivotDrawer";

export const MobileAstroPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"TRANSIT" | "SCHEDULE" | "RULES">("TRANSIT");

  const { data: snapshot, isLoading } = useQuery<MoonTransitSnapshot>({
    queryKey: ["mobile-moon-transit"],
    queryFn: async () => {
      const res = await api.get("/v1/astro/moon-transit");
      return res.data;
    },
    refetchInterval: 30000,
    staleTime: 15000,
  });

  const current = snapshot?.current;
  const schedule = snapshot?.upcoming_schedule || [];
  const calculatedAt = snapshot?.calculated_at_ist || "Live";

  return (
    <div
      style={{
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: 16,
        paddingBottom: "80px",
        color: "var(--text)",
      }}
    >
      {/* Mobile Top Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingBottom: 12,
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "rgba(0, 229, 255, 0.12)",
              border: "1px solid rgba(0, 229, 255, 0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--ba-cyan)",
            }}
          >
            <Moon size={16} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: 0.2 }}>
              Moon Transit Watch
            </div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 1 }}>
              Lahiri Sidereal Ephemeris (Watch Only)
            </div>
          </div>
        </div>

        <span
          style={{
            fontSize: 9,
            fontWeight: 800,
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

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          borderRadius: 8,
          background: "var(--surface2)",
          padding: 3,
          border: "1px solid var(--border)",
        }}
      >
        <button
          onClick={() => setActiveTab("TRANSIT")}
          style={{
            flex: 1,
            padding: "8px 0",
            fontSize: 11,
            fontWeight: 700,
            borderRadius: 6,
            background: activeTab === "TRANSIT" ? "var(--surface)" : "transparent",
            color: activeTab === "TRANSIT" ? "var(--ba-cyan)" : "var(--muted)",
            border: activeTab === "TRANSIT" ? "1px solid var(--border)" : "none",
            cursor: "pointer",
            transition: "all 0.15s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
          }}
        >
          <Compass size={12} />
          <span>Transit</span>
        </button>

        <button
          onClick={() => setActiveTab("SCHEDULE")}
          style={{
            flex: 1,
            padding: "8px 0",
            fontSize: 11,
            fontWeight: 700,
            borderRadius: 6,
            background: activeTab === "SCHEDULE" ? "var(--surface)" : "transparent",
            color: activeTab === "SCHEDULE" ? "var(--ba-cyan)" : "var(--muted)",
            border: activeTab === "SCHEDULE" ? "1px solid var(--border)" : "none",
            cursor: "pointer",
            transition: "all 0.15s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
          }}
        >
          <Calendar size={12} />
          <span>7-Day Schedule</span>
        </button>

        <button
          onClick={() => setActiveTab("RULES")}
          style={{
            flex: 1,
            padding: "8px 0",
            fontSize: 11,
            fontWeight: 700,
            borderRadius: 6,
            background: activeTab === "RULES" ? "var(--surface)" : "transparent",
            color: activeTab === "RULES" ? "var(--ba-cyan)" : "var(--muted)",
            border: activeTab === "RULES" ? "1px solid var(--border)" : "none",
            cursor: "pointer",
            transition: "all 0.15s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
          }}
        >
          <BookOpen size={12} />
          <span>Rules</span>
        </button>
      </div>

      {isLoading && !current && (
        <div style={{ textAlign: "center", padding: "40px 0", color: "var(--muted)", fontSize: 12 }}>
          Calculating Swiss Ephemeris lunar telemetry...
        </div>
      )}

      {current && activeTab === "TRANSIT" && (
        <>
          {/* Hero Position Card */}
          <div
            style={{
              background: "linear-gradient(135deg, rgba(0, 229, 255, 0.08) 0%, rgba(124, 77, 255, 0.08) 100%)",
              border: "1px solid rgba(0, 229, 255, 0.25)",
              borderRadius: 10,
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)" }}>
                  Active Moon Sign
                </div>
                <div style={{ fontSize: 20, fontWeight: 800, color: "var(--text)", marginTop: 2, display: "flex", alignItems: "center", gap: 6 }}>
                  <span>{current.rashi}</span>
                  <span style={{ fontSize: 13, fontWeight: 500, color: "var(--ba-cyan)" }}>({current.rashi_sanskrit})</span>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>
                  Degree in Sign
                </div>
                <div style={{ fontSize: 18, fontWeight: 800, fontFamily: "monospace", color: "var(--green)" }}>
                  {current.degree_dms}
                </div>
              </div>
            </div>

            {/* Quick Metrics Grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(2, 1fr)",
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
                <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>Rashi Lord</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 1 }}>
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
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 1 }}>
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
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 1 }}>
                  {current.nakshatra_lord}
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
                <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>KP Sub-Lord</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 1 }}>
                  {current.kp_sub_lord}
                </div>
              </div>
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 10,
                color: "var(--muted)",
                paddingTop: 4,
              }}
            >
              <span>Daily Speed: <strong style={{ color: "var(--text)" }}>{current.daily_speed_dms}/d</strong></span>
              <span>Total Lon: <strong style={{ color: "var(--text)" }}>{current.total_longitude}°</strong></span>
            </div>
          </div>

          {/* Rashi Transit Progress Card */}
          <div
            style={{
              background: "var(--surface2)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Clock size={13} style={{ color: "var(--ba-cyan)" }} />
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>
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
                height: 7,
                borderRadius: 4,
                background: "rgba(255, 255, 255, 0.08)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${Math.min(100, Math.max(0, current.rashi_progress_pct))}%`,
                  height: "100%",
                  background: "linear-gradient(90deg, var(--ba-cyan) 0%, var(--green) 100%)",
                  borderRadius: 4,
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)" }}>
              <span>Ingress: {current.rashi_ingress_ist}</span>
              <span>Egress: {current.rashi_egress_ist}</span>
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                paddingTop: 6,
                borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                fontSize: 11,
              }}
            >
              <span style={{ color: "var(--muted)" }}>Remaining in {current.rashi}:</span>
              <span
                style={{
                  fontWeight: 800,
                  color: "var(--ba-yellow, #ffb300)",
                  fontFamily: "monospace",
                  background: "rgba(255, 179, 0, 0.1)",
                  padding: "1px 6px",
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
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Layers size={13} style={{ color: "var(--purple, #b388ff)" }} />
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>
                  Nakshatra ({current.nakshatra} #{current.nakshatra_number})
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
                height: 7,
                borderRadius: 4,
                background: "rgba(255, 255, 255, 0.08)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${Math.min(100, Math.max(0, current.nakshatra_progress_pct))}%`,
                  height: "100%",
                  background: "linear-gradient(90deg, #7c4dff 0%, #b388ff 100%)",
                  borderRadius: 4,
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)" }}>
              <span>Entered: {current.nakshatra_ingress_ist}</span>
              <span>Exits: {current.nakshatra_egress_ist}</span>
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                paddingTop: 6,
                borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                fontSize: 11,
              }}
            >
              <span style={{ color: "var(--muted)" }}>Remaining in {current.nakshatra}:</span>
              <span
                style={{
                  fontWeight: 800,
                  color: "var(--purple, #b388ff)",
                  fontFamily: "monospace",
                  background: "rgba(179, 136, 255, 0.1)",
                  padding: "1px 6px",
                  borderRadius: 4,
                  border: "1px solid rgba(179, 136, 255, 0.25)",
                }}
              >
                {current.nakshatra_remaining_str}
              </span>
            </div>
          </div>

          {/* Next Ingress Card */}
          <div
            style={{
              background: "rgba(0, 229, 255, 0.04)",
              border: "1px solid rgba(0, 229, 255, 0.2)",
              borderRadius: 10,
              padding: 12,
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase" }}>
              Next Sign Ingress
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>{current.next_rashi} ({current.next_rashi_sanskrit})</span>
              <span style={{ fontSize: 11, color: "var(--ba-cyan)", fontFamily: "monospace" }}>
                {current.rashi_egress_ist}
              </span>
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              Lord: <strong style={{ color: "var(--text)" }}>{current.next_rashi_lord}</strong> • Next Nakshatra: <strong style={{ color: "var(--text)" }}>{current.next_nakshatra}</strong> ({current.next_nakshatra_lord})
            </div>
          </div>
        </>
      )}

      {/* 7-Day Schedule Tab */}
      {activeTab === "SCHEDULE" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.4 }}>
            Next 7 Moon sign transits calculated via Swiss Ephemeris root finding:
          </div>

          {schedule.map((item, idx) => (
            <div
              key={idx}
              style={{
                background: idx === 0 ? "rgba(0, 229, 255, 0.05)" : "var(--surface2)",
                border: idx === 0 ? "1px solid rgba(0, 229, 255, 0.3)" : "1px solid var(--border)",
                borderRadius: 8,
                padding: 12,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, color: "var(--text)" }}>{item.rashi}</span>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>({item.rashi_sanskrit})</span>
                </div>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "var(--ba-cyan)",
                    background: "rgba(0, 229, 255, 0.1)",
                    padding: "2px 6px",
                    borderRadius: 4,
                  }}
                >
                  Lord: {item.rashi_lord}
                </span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)" }}>
                <span>Ingress: <strong style={{ color: "var(--text)", fontFamily: "monospace" }}>{item.ingress_ist}</strong></span>
                <span>Duration: <strong style={{ color: "var(--text)", fontFamily: "monospace" }}>{item.duration_hours}h</strong></span>
              </div>

              <div style={{ fontSize: 10, color: "var(--muted)" }}>
                Egress: <strong style={{ color: "var(--text)", fontFamily: "monospace" }}>{item.egress_ist}</strong>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Custom Rules Tab */}
      {activeTab === "RULES" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div
            style={{
              background: "rgba(0, 229, 255, 0.06)",
              border: "1px solid rgba(0, 229, 255, 0.25)",
              borderRadius: 8,
              padding: 12,
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ba-cyan)", fontWeight: 700, fontSize: 12 }}>
              <Sparkles size={14} />
              <span>User Custom Rules & Formula Extension</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--text)", lineHeight: 1.4 }}>
              Reserved section for user trading rules, Gann lunar degree triggers, Nakshatra market biases, and Lunar Day (Tithi) indicators.
            </div>
          </div>

          <div
            style={{
              background: "var(--surface2)",
              border: "1px dashed var(--border)",
              borderRadius: 8,
              padding: 12,
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
              1. Gann Lunar Price-Time Angles
            </div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
              Awaiting user angular harmonic rules (0°, 90°, 180°, 270°).
            </div>
          </div>

          <div
            style={{
              background: "var(--surface2)",
              border: "1px dashed var(--border)",
              borderRadius: 8,
              padding: 12,
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
              2. Moon-Gandanta Junction Sensitivity
            </div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
              Critical 0° Water-Fire transitions (Cancer-Leo, Scorpio-Sagittarius, Pisces-Aries).
            </div>
          </div>

          <div
            style={{
              background: "var(--surface2)",
              border: "1px dashed var(--border)",
              borderRadius: 8,
              padding: 12,
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
              3. Nakshatra Directional Trading Biases
            </div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
              Custom bullish, bearish, or rangebound classification per Nakshatra / Pada.
            </div>
          </div>

          <div
            style={{
              background: "var(--surface2)",
              border: "1px dashed var(--border)",
              borderRadius: 8,
              padding: 12,
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
              4. Vedic Tithi & Lunar Phase Biases
            </div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
              Shukla / Krishna Paksha and Tithi progression relative to the Sun.
            </div>
          </div>
        </div>
      )}

      {/* Footer Timestamp */}
      <div
        style={{
          paddingTop: 8,
          borderTop: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: "var(--muted)",
        }}
      >
        <span>Calculated: {calculatedAt}</span>
        <span style={{ color: "var(--ba-cyan)", fontWeight: 600 }}>Lahiri Sidereal</span>
      </div>
    </div>
  );
};
