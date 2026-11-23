import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import { Compass } from "lucide-react";
import { AstroMarketSignal, AstroPivotDrawer } from "./AstroPivotDrawer";

export const AstroTelemetryBadge: React.FC = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Poll astro snapshot every 5 minutes (300,000 ms)
  const { data: signal, isError } = useQuery<AstroMarketSignal>({
    queryKey: ["astro-snapshot"],
    queryFn: async () => {
      const res = await api.get("/v1/astro/snapshot");
      return res.data;
    },
    refetchInterval: 300000,
    staleTime: 120000,
  });

  if (isError || !signal) {
    return null;
  }

  const isVol = signal.volatility_alert;
  const isBullish = signal.regime_bias === "BULLISH_TAILWIND";

  const statusColor = isVol
    ? "var(--red)"
    : isBullish
    ? "var(--green)"
    : "var(--text)";

  const statusBg = isVol
    ? "rgba(255, 59, 87, 0.12)"
    : isBullish
    ? "rgba(0, 230, 118, 0.12)"
    : "var(--surface2)";

  const statusBorder = isVol
    ? "rgba(255, 59, 87, 0.35)"
    : isBullish
    ? "rgba(0, 230, 118, 0.35)"
    : "var(--border)";

  const regimeLabel = isVol
    ? "HIGH VOL"
    : isBullish
    ? "BULLISH"
    : "NEUTRAL";

  return (
    <>
      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        title="Financial Astrology & Cyclical Market Timing Radar (Watch Purpose Only) - Click to open Intraday Pivots & Aspects"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 7,
          padding: "4px 8px",
          background: statusBg,
          border: `1px solid ${statusBorder}`,
          borderRadius: 4,
          fontSize: 10,
          fontWeight: 700,
          color: "var(--text)",
          cursor: "pointer",
          letterSpacing: 0.3,
          transition: "all 0.15s ease",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            color: isVol ? "var(--red)" : "var(--ba-cyan)",
          }}
        >
          <Compass size={12} />
        </span>

        {/* Regime Pill */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontWeight: 800,
            color: statusColor,
          }}
        >
          <span
            style={{
              width: 5,
              height: 5,
              borderRadius: "50%",
              background: statusColor,
              boxShadow: isVol
                ? "0 0 5px var(--red)"
                : isBullish
                ? "0 0 5px var(--green)"
                : "none",
            }}
          />
          {regimeLabel}
        </span>

        <span style={{ color: "var(--border)", fontSize: 10 }}>|</span>

        {/* Moon Nakshatra & KP Sub-Lord */}
        <span style={{ color: "var(--muted)", fontWeight: 600 }}>
          {signal.moon_nakshatra} /{" "}
          <strong style={{ color: "var(--text)", fontWeight: 700 }}>
            {signal.moon_kp_sub_lord}
          </strong>
        </span>

        {/* Net Sentiment Score */}
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 9,
            fontWeight: 700,
            padding: "1px 4px",
            borderRadius: 2,
            background: "rgba(255, 255, 255, 0.06)",
            color:
              signal.net_sentiment_score > 0
                ? "var(--green)"
                : signal.net_sentiment_score < 0
                ? "var(--red)"
                : "var(--muted)",
          }}
        >
          {signal.net_sentiment_score > 0
            ? `+${signal.net_sentiment_score}`
            : signal.net_sentiment_score}
        </span>
      </button>

      {/* Expandable Slide-over Drawer */}
      <AstroPivotDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        signal={signal}
      />
    </>
  );
};
