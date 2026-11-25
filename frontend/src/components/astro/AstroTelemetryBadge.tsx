import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import { Moon } from "lucide-react";
import { MoonTransitSnapshot, AstroPivotDrawer } from "./AstroPivotDrawer";

export const AstroTelemetryBadge: React.FC = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Poll Moon transit telemetry every 60 seconds
  const { data: snapshot, isError } = useQuery<MoonTransitSnapshot>({
    queryKey: ["moon-transit-badge"],
    queryFn: async () => {
      const res = await api.get("/v1/astro/moon-transit");
      return res.data;
    },
    refetchInterval: 60000,
    staleTime: 30000,
  });

  if (isError || !snapshot?.current) {
    return null;
  }

  const current = snapshot.current;

  return (
    <>
      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        title={`Moon Transit Watch: ${current.rashi} (${current.rashi_sanskrit}) ${current.degree_dms} | Lord: ${current.rashi_lord} | Nakshatra: ${current.nakshatra} (Pada ${current.pada}) - Lord: ${current.nakshatra_lord} | ${current.rashi_remaining_str} remaining until ${current.next_rashi}. Click for transit schedule & telemetry.`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 7,
          padding: "4px 9px",
          background: "rgba(0, 229, 255, 0.08)",
          border: "1px solid rgba(0, 229, 255, 0.28)",
          borderRadius: 4,
          fontSize: 11,
          fontWeight: 700,
          color: "var(--text)",
          cursor: "pointer",
          letterSpacing: 0.2,
          transition: "all 0.15s ease",
        }}
      >
        {/* Moon Icon */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            color: "var(--ba-cyan)",
          }}
        >
          <Moon size={12} />
        </span>

        {/* Sign & Lord Pill */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontWeight: 800,
            color: "var(--ba-cyan)",
          }}
        >
          <span>{current.rashi}</span>
          <span style={{ fontFamily: "monospace", fontSize: 10, color: "var(--text)" }}>
            {current.degree_dms}
          </span>
          <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: 600 }}>
            ({current.rashi_lord})
          </span>
        </span>

        <span style={{ color: "var(--border)", fontSize: 11 }}>|</span>

        {/* Nakshatra & Lord */}
        <span style={{ color: "var(--muted)", fontWeight: 600, fontSize: 10 }}>
          <span style={{ color: "var(--text)", fontWeight: 700 }}>{current.nakshatra}</span>
          <span> P{current.pada}</span>
          <span> ({current.nakshatra_lord})</span>
        </span>

        {/* Time Remaining Pill */}
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 9,
            fontWeight: 700,
            padding: "1px 5px",
            borderRadius: 3,
            background: "rgba(255, 179, 0, 0.12)",
            color: "var(--ba-yellow, #ffb300)",
            border: "1px solid rgba(255, 179, 0, 0.3)",
          }}
        >
          {current.rashi_remaining_str}
        </span>
      </button>

      {/* Expandable Slide-over Drawer */}
      <AstroPivotDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </>
  );
};
