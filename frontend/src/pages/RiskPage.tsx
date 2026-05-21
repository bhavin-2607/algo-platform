import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

export default function RiskPage() {
  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">RISK MANAGEMENT</h1>
          <p className="page-sub">Loss limits, exposure controls & emergency kill switch</p>
        </div>
      </div>
      <RiskOverview />
    </Layout>
  );
}

/* ── Overview grid ───────────────────────────────────────────────────────── */
function RiskOverview() {
  const { data: overview, isLoading } = useQuery({
    queryKey: ["risk-overview"],
    queryFn: () => api.get("/risk/overview/all").then(r => r.data),
    refetchInterval: 10_000,
  });

  const { data: myStrategies } = useQuery({
    queryKey: ["my-strategies"],
    queryFn: () => api.get("/strategies/my").then(r => r.data),
  });

  if (isLoading) return <div style={{ color: "var(--muted)", padding: 20, fontSize: 12 }}>Loading risk data...</div>;

  if (!overview?.length) {
    return (
      <div className="card">
        <div style={{ padding: "48px 24px", textAlign: "center" }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⚠</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>No active strategies</div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>
            Assign and start a strategy to manage its risk settings here.
          </div>
        </div>
      </div>
    );
  }

  // Build a name map from strategies
  const nameMap: Record<string, string> = {};
  myStrategies?.forEach((s: any) => { nameMap[s.id] = s.strategy_name; });

  return (
    <div>
      {/* Platform-wide summary */}
      <div className="stats-grid" style={{ marginBottom: 24 }}>
        <StatCard
          label="TOTAL STRATEGIES"
          value={overview.length}
          sub="configured"
        />
        <StatCard
          label="ACTIVE"
          value={overview.filter((s: any) => s.status === "active").length}
          sub="running now"
          color="green"
        />
        <StatCard
          label="KILL SWITCH"
          value={overview.filter((s: any) => s.kill_switch_active).length}
          sub="triggered"
          color={overview.some((s: any) => s.kill_switch_active) ? "red" : undefined}
        />
        <StatCard
          label="TODAY'S P&L"
          value={`₹${overview.reduce((s: number, r: any) => s + r.daily_pnl, 0).toLocaleString()}`}
          sub="across all strategies"
          color={overview.reduce((s: number, r: any) => s + r.daily_pnl, 0) >= 0 ? "green" : "red"}
        />
      </div>

      {/* Per-strategy risk cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {overview.map((r: any) => (
          <StrategyRiskCard
            key={r.map_id}
            data={r}
            name={nameMap[r.map_id] ?? "Strategy"}
          />
        ))}
      </div>
    </div>
  );
}

/* ── Per-strategy card ───────────────────────────────────────────────────── */
function StrategyRiskCard({ data, name }: { data: any; name: string }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    daily_loss_limit:       data.daily_loss_limit,
    max_exposure:           data.max_exposure,
    max_quantity:           data.max_quantity,
    max_consecutive_losses: data.max_consecutive_losses,
  });
  const set = (k: string) => (v: any) => setForm(f => ({ ...f, [k]: v }));

  const { data: events } = useQuery({
    queryKey: ["risk-events", data.map_id],
    queryFn: () => api.get(`/risk/${data.map_id}/events`).then(r => r.data),
    enabled: editing,
  });

  const saveMutation = useMutation({
    mutationFn: () => api.put(`/risk/${data.map_id}`, form),
    onSuccess: () => {
      toast.success("Risk limits updated");
      qc.invalidateQueries({ queryKey: ["risk-overview"] });
      setEditing(false);
    },
    onError: () => toast.error("Failed to update limits"),
  });

  const killMutation = useMutation({
    mutationFn: () => api.post(`/risk/${data.map_id}/kill`),
    onSuccess: () => {
      toast.success("Kill switch activated — strategy stopped");
      qc.invalidateQueries({ queryKey: ["risk-overview"] });
      qc.invalidateQueries({ queryKey: ["my-strategies"] });
    },
    onError: () => toast.error("Failed to activate kill switch"),
  });

  const resetMutation = useMutation({
    mutationFn: () => api.post(`/risk/${data.map_id}/reset`),
    onSuccess: () => {
      toast.success("Kill switch reset — strategy can be restarted");
      qc.invalidateQueries({ queryKey: ["risk-overview"] });
    },
    onError: () => toast.error("Failed to reset"),
  });

  const killed = data.kill_switch_active;
  const pnlPct = data.pnl_used_pct ?? 0;
  const pnlColor = pnlPct >= 80 ? "var(--red)" : pnlPct >= 50 ? "var(--yellow)" : "var(--green)";

  return (
    <div className={`card${killed ? " strategy-card" : ""}`}
      style={killed ? { borderColor: "rgba(255,68,102,0.4)" } : {}}>
      {/* Header */}
      <div className="card-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="card-title">{name}</span>
          <span className={`badge ${data.status === "active" ? "badge-green" : "badge-gray"}`}>
            {data.status.toUpperCase()}
          </span>
          <span className={`badge ${data.paper_trading ? "badge-yellow" : "badge-red"}`}>
            {data.paper_trading ? "PAPER" : "LIVE"}
          </span>
          {killed && <span className="badge badge-red">⚠ KILLED</span>}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {killed ? (
            <button className="connect-btn" onClick={() => resetMutation.mutate()}
              disabled={resetMutation.isPending}>
              {resetMutation.isPending ? "RESETTING..." : "↺ RESET"}
            </button>
          ) : (
            <button onClick={() => killMutation.mutate()} disabled={killMutation.isPending}
              style={{
                padding: "6px 14px", background: "rgba(255,68,102,0.1)",
                border: "1px solid rgba(255,68,102,0.4)", color: "var(--red)",
                fontFamily: "var(--font)", fontSize: 11, letterSpacing: 1,
                cursor: "pointer", transition: "all 0.15s",
              }}>
              {killMutation.isPending ? "..." : "⏹ KILL"}
            </button>
          )}
          <button className="connect-btn" onClick={() => setEditing(v => !v)}>
            {editing ? "✕ CANCEL" : "⚙ CONFIGURE"}
          </button>
        </div>
      </div>

      <div style={{ padding: "20px 20px 0" }}>
        {/* Daily loss meter */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontSize: 10, letterSpacing: 2, color: "var(--muted)" }}>DAILY LOSS USED</span>
            <span style={{ fontSize: 11, color: pnlColor, fontWeight: 600 }}>
              ₹{Math.abs(data.daily_pnl).toLocaleString()} / ₹{data.daily_loss_limit.toLocaleString()} ({pnlPct}%)
            </span>
          </div>
          <div style={{
            height: 6, background: "var(--surface2)",
            border: "1px solid var(--border)", borderRadius: 0,
          }}>
            <div style={{
              height: "100%", width: `${Math.min(pnlPct, 100)}%`,
              background: pnlColor,
              transition: "width 0.5s ease",
              boxShadow: `0 0 8px ${pnlColor}`,
            }} />
          </div>
        </div>

        {/* Risk stats row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 20 }}>
          <RiskStat label="MAX QTY" value={data.max_quantity} unit="shares" />
          <RiskStat label="MAX EXPOSURE" value={`₹${(data.max_exposure/1000).toFixed(0)}k`} />
          <RiskStat label="CONSEC. LOSSES" value={`${data.consecutive_losses} / ${data.max_consecutive_losses}`}
            color={data.consecutive_losses >= data.max_consecutive_losses ? "var(--red)" :
                   data.consecutive_losses > 0 ? "var(--yellow)" : undefined} />
          <RiskStat label="TODAY P&L"
            value={`${data.daily_pnl >= 0 ? "+" : ""}₹${data.daily_pnl.toLocaleString()}`}
            color={data.daily_pnl >= 0 ? "var(--green)" : "var(--red)"} />
        </div>

        {/* Edit form */}
        {editing && (
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 20, paddingBottom: 20 }}>
            <div style={{ fontSize: 11, letterSpacing: 2, color: "var(--green)", marginBottom: 16 }}>
              ADJUST RISK LIMITS
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              <RiskInput label="DAILY LOSS LIMIT (₹)" value={form.daily_loss_limit}
                onChange={v => set("daily_loss_limit")(parseFloat(v))}
                help="Stop trading after losing this much today" />
              <RiskInput label="MAX EXPOSURE (₹)" value={form.max_exposure}
                onChange={v => set("max_exposure")(parseFloat(v))}
                help="Max value of a single order" />
              <RiskInput label="MAX QUANTITY" value={form.max_quantity}
                onChange={v => set("max_quantity")(parseInt(v))}
                help="Max shares/lots per order" />
              <RiskInput label="MAX CONSECUTIVE LOSSES" value={form.max_consecutive_losses}
                onChange={v => set("max_consecutive_losses")(parseInt(v))}
                help="Trigger kill switch after N losses in a row" />
            </div>

            {/* Warning thresholds info */}
            <div className="info-box" style={{ marginBottom: 16 }}>
              <div className="info-icon">ℹ</div>
              <div>
                <div className="info-title">WHEN DO LIMITS APPLY?</div>
                <div className="info-body">
                  Changes take effect on the next signal/tick evaluation.
                  The kill switch stops the strategy immediately regardless of settings.
                  Daily counters reset automatically at 9:15 AM IST.
                </div>
              </div>
            </div>

            <button className="auth-btn" onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "SAVING..." : "SAVE LIMITS →"}
            </button>
          </div>
        )}

        {/* Risk event log */}
        {editing && events?.length > 0 && (
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16, paddingBottom: 20 }}>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "var(--muted)", marginBottom: 12 }}>
              RECENT RISK EVENTS
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {events.slice(0, 8).map((e: any) => (
                <div key={e.id} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "8px 12px",
                  background: "var(--surface2)", border: "1px solid var(--border)",
                }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <span className={`badge ${
                      e.event_type === "killed"        ? "badge-red" :
                      e.event_type === "blocked"       ? "badge-yellow" :
                      e.event_type === "reset"         ? "badge-green" :
                      "badge-gray"
                    }`}>{e.event_type.toUpperCase()}</span>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>{e.reason}</span>
                  </div>
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>
                    {new Date(e.created_at).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Small components ────────────────────────────────────────────────────── */
function StatCard({ label, value, sub, color }: any) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={color === "green" ? { color: "var(--green)" } :
        color === "red" ? { color: "var(--red)" } : {}}>{value}</div>
      <div className="stat-delta neu">{sub}</div>
    </div>
  );
}

function RiskStat({ label, value, unit, color }: any) {
  return (
    <div style={{ padding: "12px 14px", background: "var(--surface2)", border: "1px solid var(--border)" }}>
      <div style={{ fontSize: 9, letterSpacing: 2, color: "var(--muted)", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: color ?? "var(--text)" }}>
        {value} {unit && <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: 400 }}>{unit}</span>}
      </div>
    </div>
  );
}

function RiskInput({ label, value, onChange, help }: any) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input className="field-input" type="number" value={value}
        onChange={e => onChange(e.target.value)} />
      {help && <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>{help}</div>}
    </div>
  );
}
