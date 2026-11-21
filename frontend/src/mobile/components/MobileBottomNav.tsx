import React from "react";
import { Zap, ListOrdered } from "lucide-react";

export type MobileTab = "algo" | "watchlist";

interface MobileBottomNavProps {
  currentTab: MobileTab;
  onChangeTab: (tab: MobileTab) => void;
  activeAlgoCount: number;
  watchlistCount: number;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  currentTab,
  onChangeTab,
  activeAlgoCount,
  watchlistCount,
}) => {
  return (
    <nav className="mobile-bottom-bar px-6 pt-2 flex items-center justify-around select-none">
      {/* Algo Window Tab */}
      <button
        type="button"
        onClick={() => onChangeTab("algo")}
        className="flex-1 flex flex-col items-center justify-center py-1 transition-all active:scale-95 bg-transparent border-0 outline-hidden"
        style={{
          background: "transparent",
          border: "none",
          outline: "none",
          color: currentTab === "algo" ? "var(--green)" : "var(--muted)",
          fontWeight: currentTab === "algo" ? 700 : 500,
        }}
      >
        <div className="relative">
          <Zap
            size={21}
            style={{
              color: currentTab === "algo" ? "var(--green)" : "var(--muted)",
              fill: currentTab === "algo" ? "var(--green-dim)" : "none",
            }}
          />
          {activeAlgoCount > 0 && (
            <span
              className="absolute -top-1.5 -right-3.5 font-mono text-[9px] font-extrabold px-1.5 py-0.2 rounded-full shadow-xs"
              style={{ background: "var(--green)", color: "var(--bg)" }}
            >
              {activeAlgoCount}
            </span>
          )}
        </div>
        <span className="text-[11px] mt-1 tracking-tight">Algo Window</span>
      </button>

      {/* Watchlist Tab */}
      <button
        type="button"
        onClick={() => onChangeTab("watchlist")}
        className="flex-1 flex flex-col items-center justify-center py-1 transition-all active:scale-95 bg-transparent border-0 outline-hidden"
        style={{
          background: "transparent",
          border: "none",
          outline: "none",
          color: currentTab === "watchlist" ? "var(--green)" : "var(--muted)",
          fontWeight: currentTab === "watchlist" ? 700 : 500,
        }}
      >
        <div className="relative">
          <ListOrdered
            size={21}
            style={{
              color: currentTab === "watchlist" ? "var(--green)" : "var(--muted)",
            }}
          />
          {watchlistCount > 0 && (
            <span
              className="absolute -top-1.5 -right-3.5 font-mono text-[9px] font-bold px-1.5 py-0.2 rounded-full"
              style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
            >
              {watchlistCount}
            </span>
          )}
        </div>
        <span className="text-[11px] mt-1 tracking-tight">Watchlist</span>
      </button>
    </nav>
  );
};
