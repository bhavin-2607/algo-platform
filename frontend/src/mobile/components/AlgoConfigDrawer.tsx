import React, { useState, useMemo } from "react";
import { X, RotateCcw, Trash2, Check, AlertTriangle } from "lucide-react";
import { resolveLotSize } from "@/utils/lotSize";

interface AlgoRowData {
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

  const lotSize = useMemo(() => resolveLotSize(row.symbol, row.segment, row.lot_size), [row]);
  const qtyPresets = useMemo(() => {
    if (lotSize > 1) {
      return [1, 2, 3, 4, 5, 10].map((m) => ({ qty: m * lotSize, label: `${m}L (${m * lotSize})` }));
    }
    return [1, 10, 25, 50, 100, 250].map((q) => ({ qty: q, label: String(q) }));
  }, [lotSize]);

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
    <div className="mobile-drawer-overlay">
      <div
        className="w-full max-w-lg mobile-drawer-content p-5 space-y-4"
        style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-base font-extrabold" style={{ color: "var(--text)" }}>{row.symbol}</span>
              <span
                className="text-[10px] px-2 py-0.5 rounded font-mono font-medium"
                style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
              >
                {(row.segment?.includes("MCX") || row.exchange === "MCX") ? "MCX" : row.exchange}
              </span>
            </div>
            <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>Configure Algo Parameters</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full transition-all active:scale-95"
            style={{ background: "var(--surface2)", color: "var(--muted)" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Quantity Controls */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>Order Quantity</label>
            <span className="text-[11px] font-mono font-bold" style={{ color: "var(--green)" }}>
              {lotSize > 1 ? `${Math.max(1, Math.round(qty / lotSize))} Lots = ${qty} Units` : `${qty} Shares`}
            </span>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setQty((prev) => Math.max(lotSize, prev - lotSize))}
              className="h-10 w-12 rounded-xl font-bold text-lg active:scale-95 transition-all"
              style={{ background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)" }}
            >
              -
            </button>
            <input
              type="number"
              min={lotSize}
              step={lotSize}
              value={qty}
              onChange={(e) => setQty(Math.max(lotSize, parseInt(e.target.value) || lotSize))}
              className="flex-1 h-10 rounded-xl px-3 text-center font-mono font-bold text-base focus:outline-hidden"
              style={{
                background: "var(--surface2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            />
            <button
              onClick={() => setQty((prev) => prev + lotSize)}
              className="h-10 w-12 rounded-xl font-bold text-lg active:scale-95 transition-all"
              style={{ background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)" }}
            >
              +
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {qtyPresets.map((p) => (
              <button
                key={p.qty}
                onClick={() => setQty(p.qty)}
                className="text-[11px] px-2.5 py-1 rounded-lg font-mono font-semibold transition-all active:scale-95"
                style={{
                  background: qty === p.qty ? "var(--green)" : "var(--surface2)",
                  color: qty === p.qty ? "var(--bg)" : "var(--muted)",
                  border: qty === p.qty ? "none" : "1px solid var(--border)",
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Number of Trades (1 - 5) */}
        <div className="space-y-2">
          <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>
            Number of Trades (Cycle Limit)
          </label>
          <div className="grid grid-cols-5 gap-2">
            {[1, 2, 3, 4, 5].map((count) => (
              <button
                key={count}
                onClick={() => setMaxTrades(count)}
                className="h-9 rounded-xl font-mono text-sm font-bold transition-all active:scale-95 shadow-xs"
                style={{
                  background: maxTrades === count ? "var(--green)" : "var(--surface2)",
                  color: maxTrades === count ? "var(--bg)" : "var(--muted)",
                  border: maxTrades === count ? "none" : "1px solid var(--border)",
                }}
              >
                {count}
              </button>
            ))}
          </div>
          <p className="text-[11px]" style={{ color: "var(--muted)" }}>
            Completed: <strong>{row.trades_completed}</strong> / {maxTrades} trades
          </p>
        </div>

        {/* Target Type Selector */}
        <div className="space-y-2">
          <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>Target Type</label>
          <div className="grid grid-cols-3 gap-2">
            {TARGET_OPTIONS.map((opt) => (
              <button
                key={opt}
                onClick={() => setTargetType(opt)}
                className="h-9 rounded-xl font-mono text-xs font-bold transition-all active:scale-95 shadow-xs"
                style={{
                  background: targetType === opt ? "var(--blue)" : "var(--surface2)",
                  color: targetType === opt ? "#ffffff" : "var(--muted)",
                  border: targetType === opt ? "none" : "1px solid var(--border)",
                }}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* Custom Target Input */}
        {targetType === "CUSTOM" && (
          <div className="space-y-1.5 animate-in fade-in">
            <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>
              Custom Target Price
            </label>
            <input
              type="number"
              step="0.05"
              placeholder="e.g. 24850.00"
              value={customTarget}
              onChange={(e) => setCustomTarget(e.target.value)}
              className="w-full h-10 rounded-xl px-3 font-mono text-sm focus:outline-hidden"
              style={{
                background: "var(--surface2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            />
          </div>
        )}

        {/* Custom Entry Input */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>
            Custom Entry Price (optional override)
          </label>
          <input
            type="number"
            step="0.05"
            placeholder="Leave empty for Formula Entry"
            value={customEntry}
            onChange={(e) => setCustomEntry(e.target.value)}
            className="w-full h-10 rounded-xl px-3 font-mono text-sm focus:outline-hidden"
            style={{
              background: "var(--surface2)",
              border: "1px solid var(--border)",
              color: "var(--text)",
            }}
          />
        </div>

        {/* Trade Mode Selector */}
        <div className="space-y-2">
          <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>Trade Mode</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: "FULL", label: "Full Cycle" },
              { id: "BUY_ONLY", label: "Buy Only" },
              { id: "SELL_ONLY", label: "Sell Only" },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => setTradeMode(m.id)}
                className="h-9 rounded-xl text-xs font-semibold transition-all active:scale-95"
                style={{
                  background: tradeMode === m.id ? "var(--ba-cyan, var(--blue))" : "var(--surface2)",
                  color: tradeMode === m.id ? "#ffffff" : "var(--muted)",
                  border: tradeMode === m.id ? "none" : "1px solid var(--border)",
                }}
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
            className="w-full h-11 rounded-xl font-bold text-sm flex items-center justify-center space-x-2 transition-all shadow-md active:scale-98"
            style={{
              background: "var(--green)",
              color: "var(--bg)",
            }}
          >
            <Check size={18} />
            <span>{isSaving ? "Saving..." : "Save Parameters"}</span>
          </button>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={handleResetCycle}
              className="h-10 rounded-xl font-semibold text-xs flex items-center justify-center space-x-1.5 transition-all active:scale-95"
              style={{
                background: "var(--surface2)",
                color: "var(--text)",
                border: "1px solid var(--border)",
              }}
            >
              <RotateCcw size={14} />
              <span>Reset Cycle</span>
            </button>
            <button
              onClick={handleDelete}
              className="h-10 rounded-xl font-semibold text-xs flex items-center justify-center space-x-1.5 transition-all active:scale-95"
              style={{
                background: confirmDelete ? "var(--red)" : "var(--surface2)",
                color: confirmDelete ? "#ffffff" : "var(--red)",
                border: confirmDelete ? "none" : "1px solid var(--border)",
              }}
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
