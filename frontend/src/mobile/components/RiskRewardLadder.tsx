import React from "react";

interface RiskRewardLadderProps {
  ltp: number;
  entry: number | null;
  sl: number | null;
  target: number | null;
  targetLabel?: string;
}

export const RiskRewardLadder: React.FC<RiskRewardLadderProps> = ({
  ltp,
  entry,
  sl,
  target,
  targetLabel = "T1",
}) => {
  if (!entry || !sl || !target || target <= sl) {
    return (
      <div className="flex items-center justify-between text-[11px] text-zinc-400 py-1.5 px-2 bg-zinc-900/60 rounded border border-zinc-800/80">
        <span>SL: {sl ? `₹${sl.toFixed(2)}` : "—"}</span>
        <span>Entry: {entry ? `₹${entry.toFixed(2)}` : "—"}</span>
        <span>Tgt ({targetLabel}): {target ? `₹${target.toFixed(2)}` : "—"}</span>
      </div>
    );
  }

  // Calculate percentage of progress from SL (0%) to Target (100%)
  const totalSpan = target - sl;
  const ltpProgress = Math.max(0, Math.min(100, ((ltp - sl) / totalSpan) * 100));
  const entryProgress = Math.max(0, Math.min(100, ((entry - sl) / totalSpan) * 100));

  const isProfitable = ltp >= entry;
  const progressColor = isProfitable ? "bg-emerald-500" : "bg-rose-500";

  return (
    <div className="w-full bg-zinc-950/80 p-2.5 rounded-lg border border-zinc-800/80 space-y-2">
      <div className="flex items-center justify-between text-[10px] uppercase font-mono tracking-wider">
        <span className="text-rose-400 font-semibold">SL ₹{sl.toFixed(1)}</span>
        <span className="text-zinc-400 font-medium">Entry ₹{entry.toFixed(1)}</span>
        <span className="text-emerald-400 font-semibold">{targetLabel} ₹{target.toFixed(1)}</span>
      </div>

      {/* Progress Track */}
      <div className="relative w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
        {/* Entry Marker line */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-zinc-400 z-10"
          style={{ left: `${entryProgress}%` }}
        />
        {/* LTP Progress Bar */}
        <div
          className={`h-full transition-all duration-300 ${progressColor}`}
          style={{ width: `${ltpProgress}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-[10px] text-zinc-400">
        <span>Risk: ₹{Math.max(0, entry - sl).toFixed(1)}</span>
        <span className={`font-mono font-semibold ${isProfitable ? "text-emerald-400" : "text-rose-400"}`}>
          LTP: ₹{ltp.toFixed(2)} ({ltpProgress.toFixed(0)}% to {targetLabel})
        </span>
        <span>Reward: ₹{Math.max(0, target - entry).toFixed(1)}</span>
      </div>
    </div>
  );
};
