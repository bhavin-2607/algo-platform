import React, { useState } from "react";
import { X, RotateCcw, Trash2, Check, AlertTriangle } from "lucide-react";

interface AlgoRowData {
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
  t1?: number;
  t2?: number;
  t3?: number;
  t4?: number;
  t5?: number;
}

interface AlgoConfigDrawerProps {
  row: AlgoRowData | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (rowId: string, payload: any) => Promise<void>;
  onReset: (rowId: string) => Promise<void>;
  onDelete: (rowId: string) => Promise<void>;
}

export const AlgoConfigDrawer: React.FC<AlgoConfigDrawerProps> = ({
  row,
  isOpen,
  onClose,
  onSave,
  onReset,
  onDelete,
}) => {
  if (!isOpen || !row) return null;

  const [qty, setQty] = useState<number>(row.quantity || 1);
  const [maxTrades, setMaxTrades] = useState<number>(row.number_of_trades || 1);
  const [targetType, setTargetType] = useState<string>(row.target_type || "T1");
  const [customTarget, setCustomTarget] = useState<string>(
    row.custom_target ? String(row.custom_target) : ""
  );
  const [customEntry, setCustomEntry] = useState<string>(
    row.custom_entry ? String(row.custom_entry) : ""
  );
  const [tradeMode, setTradeMode] = useState<string>(row.trade_mode || "FULL");
  const [isSaving, setIsSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const TARGET_OPTIONS = ["T1", "T2", "T3", "T4", "T5", "CUSTOM"];
  const QTY_PRESETS = [15, 25, 50, 100, 250, 500];

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave(row.id, {
        quantity: Math.max(1, qty),
        number_of_trades: Math.max(1, Math.min(5, maxTrades)),
        target_type: targetType,
        custom_target: customTarget ? parseFloat(customTarget) : null,
        custom_entry: customEntry ? parseFloat(customEntry) : null,
        trade_mode: tradeMode,
      });
      onClose();
    } finally {
      setIsSaving(false);
    }
  };

  const handleResetCycle = async () => {
    if (confirm("Reset trade cycle counter for " + row.symbol + "?")) {
      await onReset(row.id);
      onClose();
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    await onDelete(row.id);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-xs transition-opacity animate-in fade-in">
      <div className="w-full max-w-lg bg-zinc-900 border-t border-zinc-700/80 rounded-t-2xl p-5 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-base font-bold text-white">{row.symbol}</span>
              <span className="text-[10px] bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded font-mono">
                {row.exchange}
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">Configure Algo Parameters</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-400 hover:text-white rounded-full bg-zinc-800/60 active:scale-95"
          >
            <X size={18} />
          </button>
        </div>

        {/* Quantity Controls */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-zinc-300">Order Quantity</label>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setQty((prev) => Math.max(1, prev - 25))}
              className="h-10 w-12 bg-zinc-800 text-white rounded-lg font-bold text-lg active:bg-zinc-700"
            >
              -
            </button>
            <input
              type="number"
              value={qty}
              onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 1))}
              className="flex-1 h-10 bg-zinc-950 border border-zinc-700 rounded-lg px-3 text-center text-white font-mono font-bold text-base focus:border-emerald-500 focus:outline-hidden"
            />
            <button
              onClick={() => setQty((prev) => prev + 25)}
              className="h-10 w-12 bg-zinc-800 text-white rounded-lg font-bold text-lg active:bg-zinc-700"
            >
              +
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {QTY_PRESETS.map((p) => (
              <button
                key={p}
                onClick={() => setQty(p)}
                className={`text-[11px] px-2.5 py-1 rounded font-mono ${
                  qty === p
                    ? "bg-emerald-600 text-white font-semibold"
                    : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Number of Trades (1 - 5) */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-zinc-300">
            Number of Trades (Cycle Limit)
          </label>
          <div className="grid grid-cols-5 gap-2">
            {[1, 2, 3, 4, 5].map((count) => (
              <button
                key={count}
                onClick={() => setMaxTrades(count)}
                className={`h-9 rounded-lg font-mono text-sm font-semibold transition-all ${
                  maxTrades === count
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "bg-zinc-800/80 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                }`}
              >
                {count}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-zinc-400">
            Completed: {row.trades_completed} / {maxTrades} trades
          </p>
        </div>

        {/* Target Type Selector */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-zinc-300">Target Type</label>
          <div className="grid grid-cols-3 gap-2">
            {TARGET_OPTIONS.map((opt) => (
              <button
                key={opt}
                onClick={() => setTargetType(opt)}
                className={`h-9 rounded-lg font-mono text-xs font-bold transition-all ${
                  targetType === opt
                    ? "bg-blue-600 text-white shadow-sm"
                    : "bg-zinc-800/80 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* Custom Target Input */}
        {targetType === "CUSTOM" && (
          <div className="space-y-1.5 animate-in fade-in">
            <label className="text-xs font-semibold text-zinc-300">
              Custom Target Price (₹)
            </label>
            <input
              type="number"
              step="0.05"
              placeholder="e.g. 24850.00"
              value={customTarget}
              onChange={(e) => setCustomTarget(e.target.value)}
              className="w-full h-10 bg-zinc-950 border border-zinc-700 rounded-lg px-3 text-white font-mono text-sm focus:border-blue-500 focus:outline-hidden"
            />
          </div>
        )}

        {/* Custom Entry Input */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-zinc-300">
            Custom Entry Price (₹, optional override)
          </label>
          <input
            type="number"
            step="0.05"
            placeholder="Leave empty for Formula Entry"
            value={customEntry}
            onChange={(e) => setCustomEntry(e.target.value)}
            className="w-full h-10 bg-zinc-950 border border-zinc-700 rounded-lg px-3 text-white font-mono text-sm focus:border-blue-500 focus:outline-hidden"
          />
        </div>

        {/* Trade Mode Selector */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-zinc-300">Trade Mode</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: "FULL", label: "Full Cycle" },
              { id: "BUY_ONLY", label: "Buy Only" },
              { id: "SELL_ONLY", label: "Sell Only" },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => setTradeMode(m.id)}
                className={`h-9 rounded-lg text-xs font-medium ${
                  tradeMode === m.id
                    ? "bg-zinc-100 text-zinc-900 font-bold"
                    : "bg-zinc-800 text-zinc-400"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="pt-2 space-y-2.5">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="w-full h-11 bg-emerald-600 hover:bg-emerald-500 active:scale-98 text-white rounded-xl font-semibold text-sm flex items-center justify-center space-x-2 transition-all shadow-md"
          >
            <Check size={18} />
            <span>{isSaving ? "Saving..." : "Save Parameters"}</span>
          </button>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={handleResetCycle}
              className="h-10 bg-zinc-800 hover:bg-zinc-700 active:scale-98 text-zinc-300 rounded-lg font-medium text-xs flex items-center justify-center space-x-1.5"
            >
              <RotateCcw size={14} />
              <span>Reset Cycle</span>
            </button>
            <button
              onClick={handleDelete}
              className={`h-10 rounded-lg font-medium text-xs flex items-center justify-center space-x-1.5 transition-all ${
                confirmDelete
                  ? "bg-rose-600 text-white font-bold"
                  : "bg-zinc-800 hover:bg-rose-950/60 text-rose-400"
              }`}
            >
              {confirmDelete ? <AlertTriangle size={14} /> : <Trash2 size={14} />}
              <span>{confirmDelete ? "Confirm Delete?" : "Delete Script"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
