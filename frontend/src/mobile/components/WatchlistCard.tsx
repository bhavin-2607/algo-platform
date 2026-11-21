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
      className="w-full bg-zinc-900/80 hover:bg-zinc-800/80 border border-zinc-800 rounded-xl p-3.5 shadow-sm active:bg-zinc-800 transition-all cursor-pointer space-y-2.5"
    >
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-white text-sm tracking-tight">{item.symbol}</span>
            <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded font-mono font-medium">
              {item.exchange}
            </span>
          </div>

          <div className="flex items-center space-x-2 mt-1">
            {signal && (
              <span
                className={`text-[9px] font-extrabold px-1.5 py-0.2 rounded uppercase flex items-center space-x-0.5 ${
                  isBuy ? "bg-emerald-950 text-emerald-400" : "bg-rose-950 text-rose-400"
                }`}
              >
                {isBuy ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                <span>{signal}</span>
              </span>
            )}
            <span className="text-[10px] text-zinc-400 font-mono">
              H: ₹{high.toFixed(1)} / L: ₹{low.toFixed(1)}
            </span>
          </div>
        </div>

        {/* Price & Change Column */}
        <div className="text-right flex items-center space-x-3">
          <div>
            <span className="text-sm font-bold font-mono text-white block">₹{ltp.toFixed(2)}</span>
            <span
              className={`text-[11px] font-mono font-semibold block ${
                isPositive ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {isPositive ? "+" : ""}
              {changePct.toFixed(2)}%
            </span>
          </div>

          {/* Quick Add to Algo Button */}
          {isAdmin && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onQuickAddToAlgo(item);
              }}
              title="Add to Algo"
              className="w-9 h-9 rounded-lg bg-emerald-950/80 hover:bg-emerald-800 text-emerald-400 hover:text-white border border-emerald-800/60 flex items-center justify-center active:scale-95 transition-all"
            >
              <Plus size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Mini Day Range Bar */}
      <div className="flex items-center space-x-2 text-[9px] text-zinc-400 font-mono">
        <span>L: ₹{low.toFixed(1)}</span>
        <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden relative">
          <div
            className={`h-full ${isPositive ? "bg-emerald-500" : "bg-rose-500"}`}
            style={{ width: `${rangeProgress}%` }}
          />
        </div>
        <span>H: ₹{high.toFixed(1)}</span>
      </div>
    </div>
  );
};
