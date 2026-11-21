import React, { useState } from "react";
import { Settings2, Power, AlertOctagon, TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { RiskRewardLadder } from "./RiskRewardLadder";

export interface AlgoRowData {
  id: string;
  symbol: string;
  exchange: string;
  segment: string;
  quantity: number;
  number_of_trades: number;
  trades_completed: number;
  is_algo_active: boolean;
  status: string;
  target_type: string;
  custom_target: number | null;
  trade_mode: string;
  entry_type: string;
  custom_entry: number | null;
  buy_price: number | null;
  sell_tgt: number | null;
  stop_loss: number | null;
  pnl: number;
  live_ltp: number;
  entry?: number;
  sl?: number;
  t1?: number;
  t2?: number;
  t3?: number;
  t4?: number;
  t5?: number;
  signal?: string;
}

interface AlgoSmartCardProps {
  row: AlgoRowData;
  isAdmin: boolean;
  onToggleActive: (rowId: string, currentActive: boolean) => Promise<void>;
  onManualOrder: (rowId: string, side: "BUY" | "SELL") => Promise<void>;
  onKill: (rowId: string) => Promise<void>;
  onOpenConfig: (row: AlgoRowData) => void;
}

export const AlgoSmartCard: React.FC<AlgoSmartCardProps> = ({
  row,
  isAdmin,
  onToggleActive,
  onManualOrder,
  onKill,
  onOpenConfig,
}) => {
  const [isToggling, setIsToggling] = useState(false);
  const [isOrdering, setIsOrdering] = useState(false);
  const [showKillConfirm, setShowKillConfirm] = useState(false);

  const ltp = row.live_ltp || row.buy_price || 0;
  const pnl = row.pnl || 0;
  const isPnlPositive = pnl >= 0;

  const handleToggle = async () => {
    if (!isAdmin || isToggling) return;
    setIsToggling(true);
    try {
      await onToggleActive(row.id, row.is_algo_active);
    } finally {
      setIsToggling(false);
    }
  };

  const handleOrder = async (side: "BUY" | "SELL") => {
    if (!isAdmin || isOrdering) return;
    setIsOrdering(true);
    try {
      await onManualOrder(row.id, side);
    } finally {
      setIsOrdering(false);
    }
  };

  const handleKill = async () => {
    if (!isAdmin) return;
    if (!showKillConfirm) {
      setShowKillConfirm(true);
      return;
    }
    await onKill(row.id);
    setShowKillConfirm(false);
  };

  // Status badge colors
  const statusColorMap: Record<string, { bg: string; text: string; dot: string }> = {
    IN_POSITION: { bg: "bg-emerald-950/70", text: "text-emerald-400", dot: "bg-emerald-400" },
    WAITING_RETURN: { bg: "bg-amber-950/70", text: "text-amber-400", dot: "bg-amber-400" },
    COMPLETED: { bg: "bg-blue-950/70", text: "text-blue-400", dot: "bg-blue-400" },
    STOPPED_SL: { bg: "bg-rose-950/70", text: "text-rose-400", dot: "bg-rose-400" },
    IDLE: { bg: "bg-zinc-800/80", text: "text-zinc-400", dot: "bg-zinc-500" },
  };
  const statusStyle = statusColorMap[row.status] || statusColorMap.IDLE;

  // Signal formatting
  const signal = (row.signal || "BUY").toUpperCase();
  const isBuySignal = signal === "BUY";

  return (
    <div className="w-full bg-zinc-900/90 border border-zinc-800 rounded-xl p-4 shadow-md space-y-3 relative overflow-hidden transition-all">
      {/* Top Bar: Symbol, Tags, Algo Switch */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <div className="flex items-center space-x-2">
            <h3 className="font-bold text-white text-base tracking-tight">{row.symbol}</h3>
            <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded font-mono font-medium">
              {row.exchange}
            </span>
            <span className="text-[10px] bg-zinc-800/80 text-zinc-400 px-1.5 py-0.5 rounded uppercase font-semibold">
              {row.trade_mode || "FULL"}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            {/* Status Pill */}
            <span className={`inline-flex items-center space-x-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold ${statusStyle.bg} ${statusStyle.text}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot} animate-pulse`} />
              <span>{row.status.replace("_", " ")}</span>
            </span>

            {/* Cycle Count */}
            <span className="text-[10px] text-zinc-400 font-mono">
              Cycle: {row.trades_completed}/{row.number_of_trades}
            </span>

            {/* Signal Badge */}
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded flex items-center space-x-0.5 ${
              isBuySignal ? "bg-emerald-950/80 text-emerald-400" : "bg-rose-950/80 text-rose-400"
            }`}>
              {isBuySignal ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
              <span>{signal}</span>
            </span>
          </div>
        </div>

        {/* Algo ON / OFF Switch */}
        <div className="flex items-center space-x-2">
          {isAdmin ? (
            <button
              onClick={handleToggle}
              disabled={isToggling}
              className={`flex items-center space-x-1 px-3 py-2 rounded-xl text-xs font-bold transition-all min-h-[44px] min-w-[76px] justify-center active:scale-95 ${
                row.is_algo_active
                  ? "bg-emerald-600 text-white shadow-emerald-900/40 shadow-sm"
                  : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Power size={14} className={row.is_algo_active ? "text-white" : "text-zinc-500"} />
              <span>{row.is_algo_active ? "ON" : "OFF"}</span>
            </button>
          ) : (
            <span className={`px-2.5 py-1 rounded text-xs font-bold ${
              row.is_algo_active ? "bg-emerald-950 text-emerald-400" : "bg-zinc-800 text-zinc-500"
            }`}>
              {row.is_algo_active ? "ALGO ON" : "ALGO OFF"}
            </span>
          )}
        </div>
      </div>

      {/* Price & PnL Metrics Grid */}
      <div className="grid grid-cols-3 gap-2 py-2 px-3 bg-zinc-950/60 rounded-lg border border-zinc-800/60">
        <div>
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Live LTP</span>
          <span className="text-base font-bold font-mono text-white">
            ₹{ltp.toFixed(2)}
          </span>
        </div>
        <div>
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Entry / Cost</span>
          <span className="text-sm font-semibold font-mono text-zinc-300">
            {row.buy_price ? `₹${row.buy_price.toFixed(2)}` : (row.entry ? `₹${row.entry.toFixed(1)}` : "—")}
          </span>
        </div>
        <div className="text-right">
          <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Unrealized P&L</span>
          <span className={`text-base font-bold font-mono ${isPnlPositive ? "text-emerald-400" : "text-rose-400"}`}>
            {isPnlPositive ? "+" : ""}₹{pnl.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Visual Risk-Reward Slider */}
      <RiskRewardLadder
        ltp={ltp}
        entry={row.buy_price || row.entry || null}
        sl={row.stop_loss || row.sl || null}
        target={row.sell_tgt || row.t1 || null}
        targetLabel={row.target_type || "T1"}
      />

      {/* Action Footer (Admin Controls) */}
      <div className="flex items-center justify-between pt-1 gap-2">
        {isAdmin && !row.is_algo_active && (
          <div className="flex items-center space-x-1.5 flex-1">
            <button
              onClick={() => handleOrder("BUY")}
              disabled={isOrdering}
              className="flex-1 h-10 bg-emerald-700 hover:bg-emerald-600 active:scale-95 text-white rounded-lg text-xs font-bold flex items-center justify-center space-x-1 transition-all"
            >
              <TrendingUp size={13} />
              <span>BUY</span>
            </button>
            <button
              onClick={() => handleOrder("SELL")}
              disabled={isOrdering}
              className="flex-1 h-10 bg-rose-700 hover:bg-rose-600 active:scale-95 text-white rounded-lg text-xs font-bold flex items-center justify-center space-x-1 transition-all"
            >
              <TrendingDown size={13} />
              <span>SELL</span>
            </button>
          </div>
        )}

        {/* Kill Switch */}
        {isAdmin && (
          <button
            onClick={handleKill}
            className={`h-10 px-3 rounded-lg text-xs font-bold flex items-center justify-center space-x-1 transition-all active:scale-95 ${
              showKillConfirm
                ? "bg-amber-600 text-white font-extrabold animate-pulse"
                : "bg-zinc-800 hover:bg-amber-950/60 text-amber-400"
            }`}
          >
            <AlertOctagon size={13} />
            <span>{showKillConfirm ? "CONFIRM KILL?" : "KILL"}</span>
          </button>
        )}

        {/* Config Trigger */}
        <button
          onClick={() => onOpenConfig(row)}
          className="h-10 px-3.5 bg-zinc-800 hover:bg-zinc-700 active:scale-95 text-zinc-300 rounded-lg text-xs font-medium flex items-center justify-center space-x-1.5 transition-all"
        >
          <Settings2 size={14} />
          <span>Config</span>
        </button>
      </div>
    </div>
  );
};
