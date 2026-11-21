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
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-xs transition-opacity animate-in fade-in">
      <div className="w-full max-w-lg bg-zinc-900 border-t border-zinc-700/80 rounded-t-2xl p-5 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-lg font-bold text-white tracking-tight">{item.symbol}</span>
              <span className="text-[10px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded font-mono">
                {item.exchange}
              </span>
            </div>
            <div className="flex items-center space-x-2 mt-1">
              <span className="text-xl font-extrabold font-mono text-white">₹{ltp.toFixed(2)}</span>
              <span
                className={`text-xs font-mono font-bold flex items-center ${
                  isPositive ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {isPositive ? "+" : ""}₹{change.toFixed(2)} ({isPositive ? "+" : ""}
                {changePct.toFixed(2)}%)
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-400 hover:text-white rounded-full bg-zinc-800/60 active:scale-95"
          >
            <X size={18} />
          </button>
        </div>

        {/* Vital Signal Indicators Strip */}
        <div className="grid grid-cols-4 gap-2 text-center">
          <div className="bg-zinc-950/80 p-2 rounded-lg border border-zinc-800">
            <span className="text-[9px] uppercase text-zinc-400 block font-semibold">Trend</span>
            <span
              className={`text-xs font-bold font-mono ${
                item.trend === "UP" ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {item.trend || "—"}
            </span>
          </div>

          <div className="bg-zinc-950/80 p-2 rounded-lg border border-zinc-800">
            <span className="text-[9px] uppercase text-zinc-400 block font-semibold">Super</span>
            <span
              className={`text-xs font-bold font-mono ${
                item.supersignal === "BUY" ? "text-emerald-400" : item.supersignal === "SELL" ? "text-rose-400" : "text-zinc-400"
              }`}
            >
              {item.supersignal || "—"}
            </span>
          </div>

          <div className="bg-zinc-950/80 p-2 rounded-lg border border-zinc-800">
            <span className="text-[9px] uppercase text-zinc-400 block font-semibold">Intra</span>
            <span
              className={`text-xs font-bold font-mono ${
                item.intrasignal === "BUY" ? "text-emerald-400" : item.intrasignal === "SELL" ? "text-rose-400" : "text-zinc-400"
              }`}
            >
              {item.intrasignal || "—"}
            </span>
          </div>

          <div className="bg-zinc-950/80 p-2 rounded-lg border border-zinc-800">
            <span className="text-[9px] uppercase text-zinc-400 block font-semibold">VWAP Sig</span>
            <span
              className={`text-xs font-bold font-mono ${
                item.vwapsignal === "BUY" ? "text-emerald-400" : item.vwapsignal === "SELL" ? "text-rose-400" : "text-zinc-400"
              }`}
            >
              {item.vwapsignal || "—"}
            </span>
          </div>
        </div>

        {/* OHLC & Price Levels */}
        <div className="space-y-2 bg-zinc-950/60 p-3 rounded-xl border border-zinc-800/60">
          <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider block">
            Day High / Low & Entry
          </span>
          <div className="grid grid-cols-4 gap-2 text-xs font-mono">
            <div>
              <span className="text-[9px] text-zinc-400 block">Open</span>
              <span className="text-zinc-200">₹{item.open?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-400 block">High</span>
              <span className="text-emerald-400">₹{item.high?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-400 block">Low</span>
              <span className="text-rose-400">₹{item.low?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-400 block">VWAP</span>
              <span className="text-zinc-200">₹{item.vwap?.toFixed(1) || "—"}</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs font-mono pt-2 border-t border-zinc-800/40">
            <div>
              <span className="text-[9px] text-zinc-400 block">Entry Level</span>
              <span className="text-emerald-400 font-bold">₹{item.entry?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-400 block">Stop Loss (SL)</span>
              <span className="text-rose-400 font-bold">₹{item.sl?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-400 block">GANN</span>
              <span className="text-blue-400 font-bold">₹{item.gann?.toFixed(1) || "—"}</span>
            </div>
          </div>
        </div>

        {/* Targets & Pivot Levels */}
        <div className="space-y-2 bg-zinc-950/60 p-3 rounded-xl border border-zinc-800/60">
          <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider block">
            Targets (T1 to T5)
          </span>
          <div className="grid grid-cols-5 gap-1.5 text-center font-mono text-xs">
            {["T1", "T2", "T3", "T4", "T5"].map((tLabel, idx) => {
              const val = [item.tgt1, item.tgt2, item.tgt3, item.tgt4, item.tgt5][idx];
              return (
                <div key={tLabel} className="bg-zinc-900 p-1.5 rounded border border-zinc-800">
                  <span className="text-[9px] text-zinc-400 block">{tLabel}</span>
                  <span className="text-emerald-400 font-semibold">{val ? `₹${val.toFixed(1)}` : "—"}</span>
                </div>
              );
            })}
          </div>

          {/* Pivot levels */}
          <div className="pt-2 border-t border-zinc-800/40 grid grid-cols-3 gap-2 text-xs font-mono">
            <div>
              <span className="text-[9px] text-zinc-400 block">Pivot (PP)</span>
              <span className="text-zinc-300">₹{item.pp?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-400 block">Resistance R1</span>
              <span className="text-blue-400">₹{item.r1?.toFixed(1) || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-400 block">Support S1</span>
              <span className="text-rose-400">₹{item.s1?.toFixed(1) || "—"}</span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="pt-2 space-y-2">
          {isAdmin && (
            <button
              onClick={handleAdd}
              disabled={isAdding || addedSuccess}
              className={`w-full h-12 rounded-xl font-bold text-sm flex items-center justify-center space-x-2 transition-all shadow-md active:scale-98 ${
                addedSuccess
                  ? "bg-emerald-600 text-white"
                  : "bg-emerald-600 hover:bg-emerald-500 text-white"
              }`}
            >
              {addedSuccess ? <Check size={18} /> : <PlusCircle size={18} />}
              <span>{addedSuccess ? "Added to Algo Window!" : "Add to Algo Window"}</span>
            </button>
          )}

          <button
            onClick={() => onRemoveFromWatchlist(item.id)}
            className="w-full h-10 text-xs font-medium text-zinc-400 hover:text-rose-400 bg-zinc-800/40 rounded-lg flex items-center justify-center"
          >
            Remove from Watchlist
          </button>
        </div>
      </div>
    </div>
  );
};
