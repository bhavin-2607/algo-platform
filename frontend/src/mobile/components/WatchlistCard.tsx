import React from "react";
import { Plus, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { WatchlistRowData } from "./SymbolDetailDrawer";

interface WatchlistCardProps {
  item: WatchlistRowData;
  isAdmin: boolean;
  onOpenDetail: (item: WatchlistRowData) => void;
  onQuickAddToAlgo: (item: WatchlistRowData) => Promise<void>;
}

export const WatchlistCard: React.FC<WatchlistCardProps> = ({
  item,
  isAdmin,
  onOpenDetail,
  onQuickAddToAlgo,
}) => {
  const ltp = item.ltp || 0;
  const pClose = item.p_close || item.close || ltp;
  const change = ltp - pClose;
  const changePct = pClose > 0 ? (change / pClose) * 100 : 0;
  const isPositive = change >= 0;

  const high = item.high || ltp;
  const low = item.low || ltp;
  const rangeSpan = high - low;
  const rangeProgress = rangeSpan > 0 ? Math.max(0, Math.min(100, ((ltp - low) / rangeSpan) * 100)) : 50;

  const signal = (item.supersignal || item.intrasignal || item.trend || "").toUpperCase();
  const isBuy = signal === "BUY" || signal === "UP";

  return (
    <div
      onClick={() => onOpenDetail(item)}
      className="mobile-card p-3.5 space-y-2.5 transition-all cursor-pointer active:scale-[0.99]"
    >
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-extrabold text-sm tracking-tight" style={{ color: "var(--text)" }}>
              {item.symbol}
            </span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium"
              style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
            >
              {item.exchange}
            </span>
          </div>

          <div className="flex items-center space-x-2 mt-1">
            {signal && (
              <span
                className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase flex items-center space-x-0.5"
                style={{
                  background: isBuy ? "var(--green-dim)" : "var(--red-dim)",
                  color: isBuy ? "var(--green)" : "var(--red)",
                  border: isBuy ? "1px solid rgba(0,230,118,0.25)" : "1px solid rgba(255,59,87,0.25)",
                }}
              >
                {isBuy ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                <span>{signal}</span>
              </span>
            )}
            <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
              H: ₹{high.toFixed(1)} / L: ₹{low.toFixed(1)}
            </span>
          </div>
        </div>

        {/* Price & Change Column */}
        <div className="text-right flex items-center space-x-3">
          <div>
            <span className="text-sm font-extrabold font-mono block" style={{ color: "var(--text)" }}>
              ₹{ltp.toFixed(2)}
            </span>
            <span
              className="text-[11px] font-mono font-bold block"
              style={{ color: isPositive ? "var(--green)" : "var(--red)" }}
            >
              {isPositive ? "+" : ""}
              {changePct.toFixed(2)}%
            </span>
          </div>

          {/* Quick Add to Algo Button */}
          {isAdmin && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onQuickAddToAlgo(item);
              }}
              title="Add directly to Algo Window"
              className="w-9 h-9 rounded-xl flex items-center justify-center active:scale-95 transition-all shadow-sm bg-transparent"
              style={{
                background: "var(--green-dim)",
                color: "var(--green)",
                border: "1px solid rgba(0, 230, 118, 0.4)",
              }}
            >
              <Plus size={16} style={{ strokeWidth: 2.5 }} />
            </button>
          )}
        </div>
      </div>

      {/* Mini Day Range Bar */}
      <div className="flex items-center space-x-2 text-[9px] font-mono" style={{ color: "var(--muted)" }}>
        <span>L: ₹{low.toFixed(1)}</span>
        <div
          className="flex-1 h-1.5 rounded-full overflow-hidden relative"
          style={{ background: "rgba(128, 128, 128, 0.2)" }}
        >
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${rangeProgress}%`,
              background: isPositive ? "var(--green)" : "var(--red)",
            }}
          />
        </div>
        <span>H: ₹{high.toFixed(1)}</span>
      </div>
    </div>
  );
};
