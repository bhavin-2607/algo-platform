import React from "react";
import { LogOut, ShieldCheck, Sun, Moon } from "lucide-react";

interface MobileHeaderProps {
  userEmail: string;
  isAdmin: boolean;
  totalPnl: number;
  activeAlgoCount: number;
  wsLatencyMs: number | null;
  wsStatus: "live" | "connecting" | "polling";
  dhanActive: boolean;
  theme: "dark" | "light";
  onToggleTheme: () => void;
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
  theme,
  onToggleTheme,
  onLogout,
}) => {
  const isPnlPositive = totalPnl >= 0;

  return (
    <header className="mobile-header-bar px-4 pt-3 pb-2.5 select-none">
      {/* Top Strip */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <img
            src="/branding/algo-symbol.svg"
            alt="Algo Platform Logo"
            className="w-8 h-8 rounded-xl shadow-sm"
            style={{ borderRadius: 9 }}
          />
          <div>
            <div className="flex items-center space-x-1.5">
              <span className="font-extrabold text-sm tracking-tight" style={{ color: "var(--text)" }}>
                ALGO <span style={{ color: "var(--ba-cyan, var(--blue))" }}>MOBILE</span>
              </span>
              {isAdmin && (
                <span
                  className="flex items-center space-x-0.5 text-[9px] px-1.5 py-0.5 rounded-full font-bold uppercase"
                  style={{
                    background: "var(--green-dim)",
                    color: "var(--green)",
                    border: "1px solid rgba(0, 230, 118, 0.3)",
                  }}
                >
                  <ShieldCheck size={10} />
                  <span>Admin</span>
                </span>
              )}
            </div>

            <div className="flex items-center space-x-2 text-[10px]" style={{ color: "var(--muted)" }}>
              {/* Latency & WS Status */}
              <span className="flex items-center space-x-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    wsStatus === "live"
                      ? "animate-pulse"
                      : ""
                  }`}
                  style={{
                    background:
                      wsStatus === "live"
                        ? "var(--green)"
                        : wsStatus === "connecting"
                        ? "var(--yellow)"
                        : "var(--muted)",
                  }}
                />
                <span style={{ color: wsStatus === "live" ? "var(--green)" : "var(--muted)" }}>
                  {wsStatus === "live"
                    ? `${wsLatencyMs ?? 38}ms`
                    : wsStatus === "connecting"
                    ? "Connecting..."
                    : "Polling"}
                </span>
              </span>

              <span>•</span>

              {/* Dhan Status */}
              <span style={{ color: dhanActive ? "var(--green)" : "var(--yellow)", fontWeight: 600 }}>
                {dhanActive ? "Dhan Active" : "Dhan Paper"}
              </span>
            </div>
          </div>
        </div>

        {/* Theme switcher & Logout */}
        <div className="flex items-center space-x-1.5">
          <button
            type="button"
            onClick={onToggleTheme}
            title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
            className="p-2 rounded-xl transition-all active:scale-95 bg-transparent"
            style={{
              background: "var(--surface2)",
              color: "var(--text)",
              border: "1px solid var(--border)",
            }}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          <button
            type="button"
            onClick={onLogout}
            title="Log out"
            className="p-2 rounded-xl transition-all active:scale-95 bg-transparent"
            style={{
              background: "var(--surface2)",
              color: "var(--red)",
              border: "1px solid var(--border)",
            }}
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>

      {/* Summary Vitals Banner */}
      <div
        className="mt-2.5 pt-2 flex items-center justify-between text-xs font-mono"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div>
          <span className="text-[10px] uppercase tracking-wider block" style={{ color: "var(--muted)" }}>
            Net MTM P&L
          </span>
          <span
            className="text-sm font-bold"
            style={{ color: isPnlPositive ? "var(--green)" : "var(--red)" }}
          >
            {isPnlPositive ? "+" : ""}₹{totalPnl.toFixed(2)}
          </span>
        </div>
        <div className="text-right">
          <span className="text-[10px] uppercase tracking-wider block" style={{ color: "var(--muted)" }}>
            Running Algos
          </span>
          <span className="text-sm font-bold" style={{ color: "var(--text)" }}>
            <span style={{ color: "var(--green)" }}>{activeAlgoCount}</span> Active
          </span>
        </div>
      </div>
    </header>
  );
};
