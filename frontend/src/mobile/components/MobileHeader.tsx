import React from "react";
import { LogOut, Activity, User, ShieldCheck } from "lucide-react";

interface MobileHeaderProps {
  userEmail: string;
  isAdmin: boolean;
  totalPnl: number;
  activeAlgoCount: number;
  wsLatencyMs: number | null;
  wsStatus: "live" | "connecting" | "polling";
  dhanActive: boolean;
  onLogout: () => void;
}

export const MobileHeader: React.FC<MobileHeaderProps> = ({
  userEmail,
  isAdmin,
  totalPnl,
  activeAlgoCount,
  wsLatencyMs,
  wsStatus,
  dhanActive,
  onLogout,
}) => {
  const isPnlPositive = totalPnl >= 0;

  return (
    <header className="sticky top-0 z-40 bg-zinc-950/95 backdrop-blur-md border-b border-zinc-800/80 px-4 pt-3 pb-2.5">
      {/* Top Strip */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center font-bold text-white text-xs tracking-wider">
            BA
          </div>
          <div>
            <div className="flex items-center space-x-1.5">
              <span className="font-extrabold text-white text-sm tracking-tight">ALGO MOBILE</span>
              {isAdmin && (
                <span className="flex items-center space-x-0.5 text-[9px] bg-emerald-950 text-emerald-400 border border-emerald-800/60 px-1 py-0.2 rounded font-semibold uppercase">
                  <ShieldCheck size={10} />
                  <span>Admin</span>
                </span>
              )}
            </div>
            <div className="flex items-center space-x-2 text-[10px] text-zinc-400">
              {/* Latency & WS Status */}
              <span className="flex items-center space-x-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    wsStatus === "live"
                      ? "bg-emerald-400 animate-pulse"
                      : wsStatus === "connecting"
                      ? "bg-amber-400"
                      : "bg-zinc-500"
                  }`}
                />
                <span>
                  {wsStatus === "live"
                    ? `${wsLatencyMs ?? 42}ms`
                    : wsStatus === "connecting"
                    ? "Connecting..."
                    : "Polling"}
                </span>
              </span>

              <span>•</span>

              {/* Dhan Status */}
              <span className={dhanActive ? "text-emerald-400 font-medium" : "text-amber-400 font-medium"}>
                {dhanActive ? "Dhan Active" : "Dhan Paper"}
              </span>
            </div>
          </div>
        </div>

        {/* User profile & Logout */}
        <div className="flex items-center space-x-2">
          <button
            onClick={onLogout}
            title="Log out"
            className="p-2 text-zinc-400 hover:text-rose-400 rounded-lg bg-zinc-900 border border-zinc-800 active:scale-95 transition-all"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>

      {/* Summary Vitals Banner */}
      <div className="mt-2.5 pt-2 border-t border-zinc-800/60 flex items-center justify-between text-xs font-mono">
        <div>
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Net MTM P&L</span>
          <span className={`text-sm font-bold ${isPnlPositive ? "text-emerald-400" : "text-rose-400"}`}>
            {isPnlPositive ? "+" : ""}₹{totalPnl.toFixed(2)}
          </span>
        </div>
        <div className="text-right">
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Running Algos</span>
          <span className="text-sm font-bold text-white">
            <span className="text-emerald-400">{activeAlgoCount}</span> Active
          </span>
        </div>
      </div>
    </header>
  );
};
