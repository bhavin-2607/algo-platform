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
    <nav className="fixed bottom-0 left-0 right-0 z-40 bg-zinc-950/95 backdrop-blur-md border-t border-zinc-800 px-6 py-2 flex items-center justify-around safe-bottom">
      {/* Algo Window Tab */}
      <button
        onClick={() => onChangeTab("algo")}
        className={`flex-1 flex flex-col items-center justify-center py-1 transition-all active:scale-95 ${
          currentTab === "algo" ? "text-emerald-400 font-bold" : "text-zinc-500 hover:text-zinc-300 font-medium"
        }`}
      >
        <div className="relative">
          <Zap size={20} className={currentTab === "algo" ? "text-emerald-400 fill-emerald-400/20" : ""} />
          {activeAlgoCount > 0 && (
            <span className="absolute -top-1.5 -right-3.5 bg-emerald-600 text-white font-mono text-[9px] font-extrabold px-1.5 py-0.2 rounded-full">
              {activeAlgoCount}
            </span>
          )}
        </div>
        <span className="text-[11px] mt-1 tracking-tight">Algo Window</span>
      </button>

      {/* Watchlist Tab */}
      <button
        onClick={() => onChangeTab("watchlist")}
        className={`flex-1 flex flex-col items-center justify-center py-1 transition-all active:scale-95 ${
          currentTab === "watchlist" ? "text-emerald-400 font-bold" : "text-zinc-500 hover:text-zinc-300 font-medium"
        }`}
      >
        <div className="relative">
          <ListOrdered size={20} className={currentTab === "watchlist" ? "text-emerald-400" : ""} />
          {watchlistCount > 0 && (
            <span className="absolute -top-1.5 -right-3.5 bg-zinc-700 text-zinc-300 font-mono text-[9px] font-bold px-1.5 py-0.2 rounded-full">
              {watchlistCount}
            </span>
          )}
        </div>
        <span className="text-[11px] mt-1 tracking-tight">Watchlist</span>
      </button>
    </nav>
  );
};
