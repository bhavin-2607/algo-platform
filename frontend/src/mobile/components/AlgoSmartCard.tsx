import React, { useState } from "react";
import { Settings2, Power, AlertOctagon, TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { RiskRewardLadder } from "./RiskRewardLadder";
import { resolveLotSize, formatQuantityWithLots } from "@/utils/lotSize";

export interface AlgoRowData {
  id: string;
  symbol: string;
  exchange: string;
  segment: string;
  quantity: number;
  lot_size?: number;
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

  // Status badge styling
  const getStatusStyle = (status: string) => {
    switch (status) {
      case "IN_POSITION":
        return { bg: "var(--green-dim)", color: "var(--green)", border: "1px solid rgba(0, 230, 118, 0.3)", dot: "var(--green)" };
      case "WAITING_RETURN":
        return { bg: "var(--yellow-dim)", color: "var(--yellow)", border: "1px solid rgba(255, 183, 3, 0.3)", dot: "var(--yellow)" };
      case "COMPLETED":
        return { bg: "var(--blue-dim)", color: "var(--blue)", border: "1px solid rgba(8, 182, 222, 0.3)", dot: "var(--blue)" };
      case "STOPPED_SL":
        return { bg: "var(--red-dim)", color: "var(--red)", border: "1px solid rgba(255, 59, 87, 0.3)", dot: "var(--red)" };
      default:
        return { bg: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)", dot: "var(--muted)" };
    }
  };
  const statusStyle = getStatusStyle(row.status);

  // Signal formatting
  const signal = (row.signal || "BUY").toUpperCase();
  const isBuySignal = signal === "BUY";

  return (
    <div className="mobile-card p-4 space-y-3 relative overflow-hidden transition-all">
      {/* Top Bar: Symbol, Tags, Algo Switch */}
      <div className="flex items-center justify-between gap-2">
        <div className="space-y-1 min-w-0 flex-1">
          <div className="flex items-center space-x-1.5 flex-wrap">
            <h3 className="font-extrabold text-sm tracking-tight truncate max-w-[150px] sm:max-w-none" style={{ color: "var(--text)" }}>
              {row.symbol}
            </h3>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium shrink-0"
              style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
            >
              {(row.segment?.includes("MCX") || row.exchange === "MCX") ? "MCX" : row.exchange}
            </span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold shrink-0"
              style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
            >
              {row.trade_mode || "FULL"}
            </span>
          </div>

          <div className="flex items-center space-x-2 flex-wrap gap-y-1">
            {/* Status Pill */}
            <span
              className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold shrink-0"
              style={{ background: statusStyle.bg, color: statusStyle.color, border: statusStyle.border }}
            >
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: statusStyle.dot }} />
              <span>{row.status.replace("_", " ")}</span>
            </span>

            {/* Cycle Count */}
            <span className="text-[10px] font-mono shrink-0" style={{ color: "var(--muted)" }}>
              Cycle: <strong>{row.trades_completed}/{row.number_of_trades}</strong>
            </span>

            {/* Signal Badge */}
            <span
              className="text-[10px] font-bold px-1.5 py-0.5 rounded flex items-center space-x-0.5 shrink-0"
              style={{
                background: isBuySignal ? "var(--green-dim)" : "var(--red-dim)",
                color: isBuySignal ? "var(--green)" : "var(--red)",
                border: isBuySignal ? "1px solid rgba(0,230,118,0.25)" : "1px solid rgba(255,59,87,0.25)",
              }}
            >
              {isBuySignal ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
              <span>{signal}</span>
            </span>
          </div>
        </div>

        {/* Algo ON / OFF Switch (Touch Target >= 48px) */}
        <div className="flex items-center shrink-0">
          {isAdmin ? (
            <button
              type="button"
              onClick={handleToggle}
              disabled={isToggling}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-bold transition-all min-h-[46px] min-w-[80px] justify-center active:scale-95 shadow-sm"
              style={{
                background: row.is_algo_active ? "var(--green)" : "var(--surface2)",
                color: row.is_algo_active ? "var(--bg)" : "var(--muted)",
                border: row.is_algo_active ? "none" : "1px solid var(--border)",
              }}
            >
              <Power size={15} style={{ strokeWidth: 2.5 }} />
              <span>{row.is_algo_active ? "ALGO ON" : "ALGO OFF"}</span>
            </button>
          ) : (
            <span
              className="px-2.5 py-1 rounded-lg text-xs font-bold"
              style={{
                background: row.is_algo_active ? "var(--green-dim)" : "var(--surface2)",
                color: row.is_algo_active ? "var(--green)" : "var(--muted)",
                border: "1px solid var(--border)",
              }}
            >
              {row.is_algo_active ? "ALGO ON" : "ALGO OFF"}
            </span>
          )}
        </div>
      </div>

      {/* Price & PnL Metrics Box */}
      <div
        className="grid grid-cols-3 gap-2 py-2.5 px-3 rounded-xl"
        style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
      >
        <div>
          <span className="text-[10px] uppercase tracking-wider block font-medium" style={{ color: "var(--muted)" }}>
            Live LTP
          </span>
          <span className="text-base font-extrabold font-mono" style={{ color: "var(--text)" }}>
            {ltp.toFixed(2)}
          </span>
        </div>
        <div>
          <span className="text-[10px] uppercase tracking-wider block font-medium" style={{ color: "var(--muted)" }}>
            Entry / Cost
          </span>
          <span className="text-sm font-semibold font-mono" style={{ color: "var(--text)" }}>
            {row.buy_price ? row.buy_price.toFixed(2) : (row.entry ? row.entry.toFixed(1) : "—")}
          </span>
        </div>
        <div className="text-right">
          <span className="text-[10px] uppercase tracking-wider block font-medium" style={{ color: "var(--muted)" }}>
            Unrealized P&L
          </span>
          <span
            className="text-base font-extrabold font-mono"
            style={{ color: isPnlPositive ? "var(--green)" : "var(--red)" }}
          >
            {isPnlPositive ? "+" : ""}{pnl.toFixed(2)}
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
        {isAdmin && !row.is_algo_active ? (
          <div className="flex items-center space-x-1.5 flex-1">
            <button
              type="button"
              onClick={() => handleOrder("BUY")}
              disabled={isOrdering}
              className="flex-1 h-10 rounded-xl text-xs font-bold flex items-center justify-center space-x-1 transition-all active:scale-95 shadow-sm"
              style={{
                background: "var(--green-dim)",
                color: "var(--green)",
                border: "1px solid rgba(0, 230, 118, 0.4)",
              }}
            >
              <TrendingUp size={14} />
              <span>BUY ({formatQuantityWithLots(row.quantity, row.lot_size || resolveLotSize(row.symbol, row.segment))})</span>
            </button>
            <button
              type="button"
              onClick={() => handleOrder("SELL")}
              disabled={isOrdering}
              className="flex-1 h-10 rounded-xl text-xs font-bold flex items-center justify-center space-x-1 transition-all active:scale-95 shadow-sm"
              style={{
                background: "var(--red-dim)",
                color: "var(--red)",
                border: "1px solid rgba(255, 59, 87, 0.4)",
              }}
            >
              <TrendingDown size={14} />
              <span>SELL ({formatQuantityWithLots(row.quantity, row.lot_size || resolveLotSize(row.symbol, row.segment))})</span>
            </button>
          </div>
        ) : (
          <div className="flex-1 text-[11px] font-mono" style={{ color: "var(--muted)" }}>
            {row.is_algo_active ? "Algo autonomous mode" : "Discretionary mode"}
          </div>
        )}

        {/* Kill Switch */}
        {isAdmin && (
          <button
            type="button"
            onClick={handleKill}
            className="h-10 px-3.5 rounded-xl text-xs font-bold flex items-center justify-center space-x-1.5 transition-all active:scale-95 shadow-sm"
            style={{
              background: showKillConfirm ? "var(--red)" : "var(--surface2)",
              color: showKillConfirm ? "#ffffff" : "var(--red)",
              border: showKillConfirm ? "none" : "1px solid var(--border)",
            }}
          >
            <AlertOctagon size={14} />
            <span>{showKillConfirm ? "CONFIRM KILL?" : "KILL"}</span>
          </button>
        )}

        {/* Config Trigger */}
        <button
          type="button"
          onClick={() => onOpenConfig(row)}
          className="h-10 px-3.5 rounded-xl text-xs font-semibold flex items-center justify-center space-x-1.5 transition-all active:scale-95"
          style={{
            background: "var(--surface2)",
            color: "var(--text)",
            border: "1px solid var(--border)",
          }}
        >
          <Settings2 size={15} />
          <span>Config</span>
        </button>
      </div>
    </div>
  );
};
