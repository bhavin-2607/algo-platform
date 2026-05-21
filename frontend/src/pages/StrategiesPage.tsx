import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { strategyApi, api } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

// ── Types ─────────────────────────────────────────────────────────────────────
interface StrategyMap {
  id: string;
  strategy_id: string;
  strategy_name: string;
  broker_account_id: string;
  params: Record<string, any>;
  status: "active" | "paused" | "stopped";
  paper_trading: boolean;
  daily_pnl: number;
  killed: boolean;
}

interface RuntimeState {
  status: string;
  daily_pnl: number;
  consecutive_losses: number;
  killed: boolean;
}

export default function StrategiesPage() {
  const qc = useQueryClient();

  const { data: myStrategies, isLoading } = useQuery({
    queryKey: ["my-strategies"],
    queryFn: () => api.get("/strategies/my").then(r => r.data as StrategyMap[]),
    refetchInterval: 10_000,
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => strategyApi.start(id),
    onSuccess: () => { toast.success("Strategy started"); qc.invalidateQueries({ queryKey: ["my-strategies"] }); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed to start"),
  });

  const stopMutation = useMutation({
    mutationFn: (id: string) => strategyApi.stop(id),
    onSuccess: () => { toast.success("Strategy stopped"); qc.invalidateQueries({ queryKey: ["my-strategies"] }); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed to stop"),
  });

  const activeCount = myStrategies?.filter(s => s.status === "active").length ?? 0;

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">STRATEGIES</h1>
          <p className="page-sub">Manage and monitor your trading algorithms</p>
        </div>
        <div className="market-status">
          <div className="market-dot" />
          <span>{activeCount} RUNNING</span>
        </div>
      </div>

      {isLoading && (
        <div style={{ color: "var(--muted)", fontSize: 12, padding: 20 }}>Loading strategies...</div>
      )}

      {!isLoading && (!myStrategies || myStrategies.length === 0) && (
        <EmptyState />
      )}

      <div className="strategy-grid">
        {myStrategies?.map((s) => (
          <StrategyCard
            key={s.id}
            strategy={s}
            onStart={() => startMutation.mutate(s.id)}
            onStop={() => stopMutation.mutate(s.id)}
            starting={startMutation.isPending}
            stopping={stopMutation.isPending}
          />
        ))}
      </div>
    </Layout>
  );
}

/* ── Strategy Card ─────────────────────────────────────────────────────────── */
function StrategyCard({ strategy: s, onStart, onStop, starting, stopping }: {
  strategy: StrategyMap;
  onStart: () => void;
  onStop: () => void;
  starting: boolean;
  stopping: boolean;
}) {
  const { accessToken } = useAuthStore();
  const [runtime, setRuntime] = useState<RuntimeState>({
    status: s.status,
    daily_pnl: s.daily_pnl ?? 0,
    consecutive_losses: 0,
    killed: s.killed ?? false,
  });
  const wsRef = useRef<WebSocket | null>(null);

  // Live status WebSocket
  useEffect(() => {
    if (s.status !== "active") return;
    const wsBase = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000").replace("http","ws");
    const url = `${wsBase}/api/ws/strategy/${s.id}?token=${accessToken}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try { setRuntime(JSON.parse(e.data)); } catch {}
    };
    return () => ws.close();
  }, [s.id, s.status, accessToken]);

  const active = s.status === "active";

  return (
    <div className={`strategy-card${active ? " active" : ""}`}>
      <div className="strategy-header">
        <div>
          <span className="strategy-tag">
            {s.paper_trading ? "PAPER" : "LIVE"} · {s.params?.symbol ?? "—"}
          </span>
          <h3 className="strategy-name">{s.strategy_name}</h3>
        </div>
        <div className={`status-pill ${active ? "running" : "stopped"}`}>
          {runtime.killed ? "⚠ KILLED" : active ? "● RUNNING" : "○ STOPPED"}
        </div>
      </div>

      {/* Params chips */}
      <div className="strategy-params">
        {Object.entries(s.params).slice(0, 4).map(([k, v]) => (
          <span key={k} className="param-chip">{k}: {String(v)}</span>
        ))}
      </div>

      {/* Live stats */}
      <div className="strategy-stats">
        <div className="s-stat">
          <div className={`s-stat-val ${runtime.daily_pnl >= 0 ? "pnl-pos" : "pnl-neg"}`}>
            {runtime.daily_pnl >= 0 ? "+" : ""}₹{runtime.daily_pnl.toLocaleString()}
          </div>
          <div className="s-stat-lbl">TODAY P&L</div>
        </div>
        <div className="s-stat">
          <div className="s-stat-val">{runtime.consecutive_losses}</div>
          <div className="s-stat-lbl">CONSEC. LOSSES</div>
        </div>
        <div className="s-stat">
          <div className={`s-stat-val ${s.paper_trading ? "" : "pnl-neg"}`}>
            {s.paper_trading ? "PAPER" : "LIVE"}
          </div>
          <div className="s-stat-lbl">MODE</div>
        </div>
      </div>

      {/* Kill switch warning */}
      {runtime.killed && (
        <div className="info-box" style={{ marginBottom: 12, borderColor: "rgba(255,68,102,0.3)", background: "rgba(255,68,102,0.05)" }}>
          <div className="info-icon" style={{ color: "var(--red)" }}>⚠</div>
          <div>
            <div className="info-title" style={{ color: "var(--red)" }}>KILL SWITCH ACTIVE</div>
            <div className="info-body">Max consecutive losses reached. Restart to resume.</div>
          </div>
        </div>
      )}

      <div className="strategy-actions">
        {active
          ? <button className="strategy-btn btn-stop"  onClick={onStop}  disabled={stopping}>⏹ {stopping ? "STOPPING..." : "STOP"}</button>
          : <button className="strategy-btn btn-start" onClick={onStart} disabled={starting}>▶ {starting ? "STARTING..." : "START"}</button>
        }
      </div>
    </div>
  );
}

/* ── Empty State ─────────────────────────────────────────────────────────────*/
function EmptyState() {
  return (
    <div className="card">
      <div style={{ padding: "48px 24px", textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>⟳</div>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>No strategies assigned yet</div>
        <div style={{ fontSize: 12, color: "var(--muted)", maxWidth: 380, margin: "0 auto" }}>
          Ask your admin to assign a strategy to your account, or use the admin panel to
          create a strategy entry and assign it.
        </div>
      </div>
    </div>
  );
}
