import React, { useState } from "react";
import { X, PlusCircle, TrendingUp, TrendingDown, Layers, Check } from "lucide-react";

export interface WatchlistRowData {
  id: string;
  symbol: string;
  exchange: string;
  segment?: string;
  token?: string;
  ltp?: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  p_close?: number;
  p_high?: number;
  p_low?: number;
  volume?: number;
  vwap?: number;
  kd?: number;
  gann?: number;
  trend?: string;
  ohlsignal?: string;
  supersignal?: string;
  intrasignal?: string;
  vwapsignal?: string;
  entry?: number;
  sl?: number;
  tgt1?: number;
  tgt2?: number;
  tgt3?: number;
  tgt4?: number;
  tgt5?: number;
  pp?: number;
  r1?: number;
  r2?: number;
  r3?: number;
  s1?: number;
  s2?: number;
  s3?: number;
  possible_tgt?: number;
}

interface SymbolDetailDrawerProps {
  item: WatchlistRowData | null;
  isOpen: boolean;
  isAdmin: boolean;
  onClose: () => void;
  onAddToAlgo: (item: WatchlistRowData) => Promise<void>;
  onRemoveFromWatchlist: (id: string) => Promise<void>;
}

export const SymbolDetailDrawer: React.FC<SymbolDetailDrawerProps> = ({
  item,
  isOpen,
  isAdmin,
  onClose,
  onAddToAlgo,
  onRemoveFromWatchlist,
}) => {
  if (!isOpen || !item) return null;

  const [isAdding, setIsAdding] = useState(false);
  const [addedSuccess, setAddedSuccess] = useState(false);

  const ltp = item.ltp || 0;
  const pClose = item.p_close || item.close || ltp;
  const change = ltp - pClose;
  const changePct = pClose > 0 ? (change / pClose) * 100 : 0;
  const isPositive = change >= 0;

  const handleAdd = async () => {
    if (isAdding) return;
    setIsAdding(true);
    try {
      await onAddToAlgo(item);
      setAddedSuccess(true);
      setTimeout(() => {
        setAddedSuccess(false);
        onClose();
      }, 1200);
    } finally {
      setIsAdding(false);
    }
  };

  return (
    <div className="mobile-drawer-overlay">
      <div
        className="w-full max-w-lg mobile-drawer-content p-5 space-y-4"
        style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-lg font-extrabold tracking-tight" style={{ color: "var(--text)" }}>{item.symbol}</span>
              <span
                className="text-[10px] px-2 py-0.5 rounded font-mono font-medium"
                style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
              >
                {item.exchange}
              </span>
            </div>
            <div className="flex items-center space-x-2 mt-1">
              <span className="text-xl font-extrabold font-mono" style={{ color: "var(--text)" }}>₹{ltp.toFixed(2)}</span>
              <span
                className="text-xs font-mono font-bold flex items-center"
                style={{ color: isPositive ? "var(--green)" : "var(--red)" }}
              >
                {isPositive ? "+" : ""}₹{change.toFixed(2)} ({isPositive ? "+" : ""}
                {changePct.toFixed(2)}%)
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full transition-all active:scale-95"
            style={{ background: "var(--surface2)", color: "var(--muted)" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Vital Signal Indicators Strip */}
        <div className="grid grid-cols-4 gap-2 text-center">
          <div className="p-2 rounded-xl" style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
            <span className="text-[9px] uppercase block font-semibold" style={{ color: "var(--muted)" }}>Trend</span>
            <span
              className="text-xs font-bold font-mono"
              style={{ color: item.trend === "UP" ? "var(--green)" : "var(--red)" }}
            >
              {item.trend || "—"}
            </span>
          </div>

          <div className="p-2 rounded-xl" style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
            <span className="text-[9px] uppercase block font-semibold" style={{ color: "var(--muted)" }}>Super</span>
            <span
              className="text-xs font-bold font-mono"
              style={{
                color: item.supersignal === "BUY" ? "var(--green)" : item.supersignal === "SELL" ? "var(--red)" : "var(--muted)",
              }}
            >
              {item.supersignal || "—"}
            </span>
          </div>

          <div className="p-2 rounded-xl" style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
            <span className="text-[9px] uppercase block font-semibold" style={{ color: "var(--muted)" }}>Intra</span>
            <span
              className="text-xs font-bold font-mono"
              style={{
                color: item.intrasignal === "BUY" ? "var(--green)" : item.intrasignal === "SELL" ? "var(--red)" : "var(--muted)",
              }}
            >
              {item.intrasignal || "—"}
            </span>
          </div>

          <div className="p-2 rounded-xl" style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
            <span className="text-[9px] uppercase block font-semibold" style={{ color: "var(--muted)" }}>VWAP Sig</span>
            <span
              className="text-xs font-bold font-mono"
              style={{
                color: item.vwapsignal === "BUY" ? "var(--green)" : item.vwapsignal === "SELL" ? "var(--red)" : "var(--muted)",
              }}
            >
              {item.vwapsignal || "—"}
            </span>
          </div>
        </div>

        {/* OHLC & Price Levels */}
        <div
          className="space-y-2 p-3.5 rounded-2xl"
          style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
        >
          <span className="text-[11px] font-bold uppercase tracking-wider block" style={{ color: "var(--muted)" }}>
            Day High / Low & Entry
          </span>
          <div className="grid grid-cols-4 gap-2 text-xs font-mono">
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>Open</span>
              <span style={{ color: "var(--text)" }}>₹{item.open?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>High</span>
              <span style={{ color: "var(--green)", fontWeight: 700 }}>₹{item.high?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>Low</span>
              <span style={{ color: "var(--red)", fontWeight: 700 }}>₹{item.low?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>VWAP</span>
              <span style={{ color: "var(--text)" }}>₹{item.vwap?.toFixed(1) || "—"}</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs font-mono pt-2" style={{ borderTop: "1px solid var(--border)" }}>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>Entry Level</span>
              <span style={{ color: "var(--green)", fontWeight: 700 }}>₹{item.entry?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>Stop Loss (SL)</span>
              <span style={{ color: "var(--red)", fontWeight: 700 }}>₹{item.sl?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>GANN</span>
              <span style={{ color: "var(--blue)", fontWeight: 700 }}>₹{item.gann?.toFixed(1) || "—"}</span>
            </div>
          </div>
        </div>

        {/* Targets & Pivot Levels */}
        <div
          className="space-y-2 p-3.5 rounded-2xl"
          style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
        >
          <span className="text-[11px] font-bold uppercase tracking-wider block" style={{ color: "var(--muted)" }}>
            Targets (T1 to T5)
          </span>
          <div className="grid grid-cols-5 gap-1.5 text-center font-mono text-xs">
            {["T1", "T2", "T3", "T4", "T5"].map((tLabel, idx) => {
              const val = [item.tgt1, item.tgt2, item.tgt3, item.tgt4, item.tgt5][idx];
              return (
                <div
                  key={tLabel}
                  className="p-1.5 rounded-lg"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                >
                  <span className="text-[9px] block" style={{ color: "var(--muted)" }}>{tLabel}</span>
                  <span style={{ color: "var(--green)", fontWeight: 700 }}>{val ? `₹${val.toFixed(1)}` : "—"}</span>
                </div>
              );
            })}
          </div>

          {/* Pivot levels */}
          <div className="pt-2 grid grid-cols-3 gap-2 text-xs font-mono" style={{ borderTop: "1px solid var(--border)" }}>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>Pivot (PP)</span>
              <span style={{ color: "var(--text)" }}>₹{item.pp?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>Resistance R1</span>
              <span style={{ color: "var(--blue)", fontWeight: 700 }}>₹{item.r1?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] block" style={{ color: "var(--muted)" }}>Support S1</span>
              <span style={{ color: "var(--red)", fontWeight: 700 }}>₹{item.s1?.toFixed(1) || "—"}</span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="pt-2 space-y-2">
          {isAdmin && (
            <button
              onClick={handleAdd}
              disabled={isAdding || addedSuccess}
              className="w-full h-12 rounded-xl font-bold text-sm flex items-center justify-center space-x-2 transition-all shadow-md active:scale-98"
              style={{
                background: "var(--green)",
                color: "var(--bg)",
              }}
            >
              {addedSuccess ? <Check size={18} /> : <PlusCircle size={18} />}
              <span>{addedSuccess ? "Added to Algo Window!" : "Add to Algo Window"}</span>
            </button>
          )}

          <button
            onClick={() => onRemoveFromWatchlist(item.id)}
            className="w-full h-10 text-xs font-semibold rounded-xl flex items-center justify-center transition-all active:scale-95"
            style={{
              background: "var(--surface2)",
              color: "var(--red)",
              border: "1px solid var(--border)",
            }}
          >
            Remove from Watchlist
          </button>
        </div>
      </div>
    </div>
  );
};
