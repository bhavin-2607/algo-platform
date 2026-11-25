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
      <div
        className="flex items-center justify-between text-[11px] py-1.5 px-3 rounded-lg font-mono"
        style={{
          background: "var(--surface2)",
          border: "1px solid var(--border)",
          color: "var(--muted)",
        }}
      >
        <span>SL: <strong style={{ color: "var(--red)" }}>{sl ? sl.toFixed(1) : "—"}</strong></span>
        <span>Entry: <strong style={{ color: "var(--text)" }}>{entry ? entry.toFixed(1) : "—"}</strong></span>
        <span>Tgt ({targetLabel}): <strong style={{ color: "var(--green)" }}>{target ? target.toFixed(1) : "—"}</strong></span>
      </div>
    );
  }

  // Calculate percentage of progress from SL (0%) to Target (100%)
  const totalSpan = target - sl;
  const ltpProgress = Math.max(0, Math.min(100, ((ltp - sl) / totalSpan) * 100));
  const entryProgress = Math.max(0, Math.min(100, ((entry - sl) / totalSpan) * 100));

  const isProfitable = ltp >= entry;

  return (
    <div
      className="w-full p-2.5 rounded-xl space-y-2"
      style={{
        background: "var(--surface2)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex items-center justify-between text-[10px] uppercase font-mono tracking-wider">
        <span style={{ color: "var(--red)", fontWeight: 700 }}>SL {sl.toFixed(1)}</span>
        <span style={{ color: "var(--muted)", fontWeight: 600 }}>Entry {entry.toFixed(1)}</span>
        <span style={{ color: "var(--green)", fontWeight: 700 }}>{targetLabel} {target.toFixed(1)}</span>
      </div>

      {/* Progress Track */}
      <div
        className="relative w-full h-2 rounded-full overflow-hidden"
        style={{ background: "rgba(128, 128, 128, 0.2)" }}
      >
        {/* Entry Marker line */}
        <div
          className="absolute top-0 bottom-0 w-1 z-10"
          style={{ left: `${entryProgress}%`, background: "var(--text)" }}
        />
        {/* LTP Progress Bar */}
        <div
          className="h-full transition-all duration-300"
          style={{
            width: `${ltpProgress}%`,
            background: isProfitable ? "var(--green)" : "var(--red)",
          }}
        />
      </div>

      <div className="grid grid-cols-3 gap-1 text-[10px] font-mono text-center" style={{ color: "var(--muted)" }}>
        <div className="text-left">
          <span>Risk: <strong>{Math.max(0, entry - sl).toFixed(1)}</strong></span>
        </div>
        <div>
          <span
            className="font-bold truncate block"
            style={{ color: isProfitable ? "var(--green)" : "var(--red)" }}
          >
            {ltp.toFixed(2)} ({ltpProgress.toFixed(0)}%)
          </span>
        </div>
        <div className="text-right">
          <span>Reward: <strong>{Math.max(0, target - entry).toFixed(1)}</strong></span>
        </div>
      </div>
    </div>
  );
};
