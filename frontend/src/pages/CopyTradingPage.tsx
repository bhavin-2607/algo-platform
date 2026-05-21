import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

export default function CopyTradingPage() {
  const [tab, setTab] = useState<"leader" | "following" | "history">("leader");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">COPY TRADING</h1>
          <p className="page-sub">TradingView webhook integration & follower management</p>
        </div>
      </div>
      <div className="tab-switcher" style={{ marginBottom: 24 }}>
        <button className={`tab-btn${tab === "leader"    ? " active" : ""}`} onClick={() => setTab("leader")}>MY WEBHOOK</button>
        <button className={`tab-btn${tab === "following" ? " active" : ""}`} onClick={() => setTab("following")}>FOLLOWING</button>
        <button className={`tab-btn${tab === "history"   ? " active" : ""}`} onClick={() => setTab("history")}>SIGNAL HISTORY</button>
      </div>
      {tab === "leader"    && <LeaderTab />}
      {tab === "following" && <FollowingTab />}
      {tab === "history"   && <HistoryTab />}
    </Layout>
  );
}

/* ── LEADER TAB — webhook setup ──────────────────────────────────────────── */
function LeaderTab() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["my-webhook"],
    queryFn: () => api.get("/signals/my-webhook").then(r => r.data),
  });

  const { data: followers } = useQuery({
    queryKey: ["followers"],
    queryFn: () => api.get("/signals/followers").then(r => r.data),
  });

  const [copied, setCopied] = useState(false);

  function copyUrl() {
    navigator.clipboard.writeText(data?.webhook_url ?? "");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (isLoading) return <Spinner />;

  return (
    <div style={{ maxWidth: 680 }}>
      {/* Webhook URL card */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title">YOUR TRADINGVIEW WEBHOOK URL</span>
          <div className="market-status" style={{ fontSize: 10 }}>
            <div className="market-dot" />
            <span>ACTIVE</span>
          </div>
        </div>
        <div style={{ padding: 24 }}>
          <p style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16, lineHeight: 1.7 }}>
            Paste this URL into TradingView's Alert → Webhook URL field.
            Every time your Pine Script fires an alert, the signal will automatically
            be sent to all your followers.
          </p>

          {/* URL display */}
          <div style={{
            display: "flex", gap: 0, marginBottom: 24,
            border: "1px solid var(--border)",
          }}>
            <div style={{
              flex: 1, padding: "12px 14px",
              background: "rgba(0,255,136,0.03)",
              fontSize: 11, color: "var(--green)",
              wordBreak: "break-all", fontFamily: "var(--font)",
            }}>
              {data?.webhook_url}
            </div>
            <button onClick={copyUrl} style={{
              padding: "12px 18px", background: copied ? "var(--green)" : "var(--green-dim)",
              border: "none", borderLeft: "1px solid var(--border)",
              color: copied ? "var(--bg)" : "var(--green)",
              fontFamily: "var(--font)", fontSize: 11, cursor: "pointer",
              letterSpacing: 1, transition: "all 0.15s", flexShrink: 0,
            }}>
              {copied ? "✓ COPIED" : "COPY"}
            </button>
          </div>

          {/* Pine Script example */}
          <div style={{ marginBottom: 0 }}>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "var(--green)", marginBottom: 10 }}>
              PINE SCRIPT ALERT MESSAGE (copy-paste into TradingView)
            </div>
            <pre style={{
              background: "var(--surface2)", border: "1px solid var(--border)",
              padding: 16, fontSize: 11, color: "#a0aec0", overflowX: "auto",
              lineHeight: 1.8, whiteSpace: "pre-wrap",
            }}>
{`{
  "token":     "${data?.webhook_token}",
  "symbol":    "{{ticker}}",
  "exchange":  "NSE",
  "direction": "{{strategy.order.action}}",
  "quantity":  {{strategy.order.contracts}},
  "price":     {{close}},
  "tag":       "MY_STRATEGY"
}`}
            </pre>
          </div>
        </div>
      </div>

      {/* Followers */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">ACTIVE FOLLOWERS</span>
          <span className="card-badge">{followers?.length ?? 0} following you</span>
        </div>
        {(!followers || followers.length === 0) ? (
          <div className="empty-state">
            No followers yet. Share your webhook setup guide with family/friends.
          </div>
        ) : (
          followers.map((f: any) => (
            <div key={f.id} className="broker-item" style={{ padding: "14px 20px" }}>
              <div>
                <div className="broker-name">{f.follower_username}</div>
                <div className="broker-id">
                  Qty multiplier: {f.qty_multiplier}x ·{" "}
                  {f.auto_execute ? "Auto-execute ON" : "Notify only"}
                </div>
              </div>
              <span className={`badge ${f.is_active ? "badge-green" : "badge-gray"}`}>
                {f.is_active ? "ACTIVE" : "PAUSED"}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* ── FOLLOWING TAB ───────────────────────────────────────────────────────── */
function FollowingTab() {
  const qc = useQueryClient();
  const { data: following, isLoading } = useQuery({
    queryKey: ["following"],
    queryFn: () => api.get("/signals/following").then(r => r.data),
  });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    leader_id: "",
    broker_account_id: "",
    auto_execute: true,
    qty_multiplier: 1.0,
  });

  const followMutation = useMutation({
    mutationFn: () => api.post("/signals/follow", {
      ...form,
      broker_account_id: form.broker_account_id || null,
      qty_multiplier: parseFloat(String(form.qty_multiplier)),
    }),
    onSuccess: () => {
      toast.success("Now following leader");
      qc.invalidateQueries({ queryKey: ["following"] });
      setShowForm(false);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed to follow"),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: any) =>
      api.patch(`/signals/following/${id}`, null, { params: { is_active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["following"] }),
  });

  const unfollowMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/signals/following/${id}`),
    onSuccess: () => {
      toast.success("Unfollowed");
      qc.invalidateQueries({ queryKey: ["following"] });
    },
  });

  // Live signal notifications via WebSocket
  const { accessToken } = useAuthStore();
  const wsRef = useRef<WebSocket | null>(null);
  const [liveSignal, setLiveSignal] = useState<any>(null);

  useEffect(() => {
    if (!accessToken) return;
    const wsBase = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000").replace("http", "ws");
    const ws = new WebSocket(`${wsBase}/api/ws/feed?token=${accessToken}`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "signal") {
          setLiveSignal(data);
          toast(`📡 Signal: ${data.direction} ${data.symbol}`, {
            icon: data.direction === "BUY" ? "🟢" : "🔴",
            duration: 5000,
          });
        }
      } catch {}
    };
    return () => ws.close();
  }, [accessToken]);

  if (isLoading) return <Spinner />;

  return (
    <div style={{ maxWidth: 680 }}>
      {/* Live signal banner */}
      {liveSignal && (
        <div style={{
          padding: "14px 20px", marginBottom: 20,
          background: liveSignal.direction === "BUY" ? "rgba(0,255,136,0.08)" : "rgba(255,68,102,0.08)",
          border: `1px solid ${liveSignal.direction === "BUY" ? "rgba(0,255,136,0.3)" : "rgba(255,68,102,0.3)"}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "var(--muted)", marginBottom: 4 }}>LATEST SIGNAL</div>
            <div style={{ fontWeight: 700, color: liveSignal.direction === "BUY" ? "var(--green)" : "var(--red)" }}>
              {liveSignal.direction} {liveSignal.quantity}x {liveSignal.symbol}
            </div>
          </div>
          <span className={`badge ${liveSignal.auto_execute ? "badge-green" : "badge-yellow"}`}>
            {liveSignal.auto_execute ? "AUTO-EXECUTED" : "NOTIFY ONLY"}
          </span>
        </div>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title">LEADERS YOU FOLLOW</span>
          <button className="connect-btn" onClick={() => setShowForm(v => !v)}>
            {showForm ? "✕ CANCEL" : "+ FOLLOW LEADER"}
          </button>
        </div>

        {showForm && (
          <div style={{ padding: "20px 20px 24px", borderBottom: "1px solid var(--border)" }}>
            <div className="field">
              <label className="field-label">LEADER USER ID</label>
              <input className="field-input" type="text" placeholder="Paste leader's user ID"
                value={form.leader_id} onChange={e => setForm(f => ({ ...f, leader_id: e.target.value }))} />
              <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
                Ask your leader to share their User ID from Settings → Profile
              </div>
            </div>

            <div className="field">
              <label className="field-label">YOUR BROKER ACCOUNT</label>
              <select className="field-input" value={form.broker_account_id}
                onChange={e => setForm(f => ({ ...f, broker_account_id: e.target.value }))}
                style={{ background: "rgba(0,255,136,0.04)", color: "var(--text)", fontFamily: "var(--font)" }}>
                <option value="">Select broker account</option>
                {brokers?.map((b: any) => (
                  <option key={b.id} value={b.id}>
                    {b.broker.toUpperCase()} — {b.paper_trading ? "Paper" : "Live"}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="field-label">QTY MULTIPLIER</label>
              <input className="field-input" type="number" min="0.1" max="10" step="0.1"
                value={form.qty_multiplier}
                onChange={e => setForm(f => ({ ...f, qty_multiplier: parseFloat(e.target.value) }))} />
              <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
                1.0 = same qty as leader · 0.5 = half · 2.0 = double
              </div>
            </div>

            <div className="field">
              <label className="field-label">EXECUTION MODE</label>
              <div style={{ display: "flex", gap: 0 }}>
                <button type="button"
                  onClick={() => setForm(f => ({ ...f, auto_execute: true }))}
                  style={{
                    flex: 1, padding: 11, fontFamily: "var(--font)", fontSize: 11,
                    letterSpacing: 1, cursor: "pointer", border: "1px solid",
                    borderRight: "none",
                    background: form.auto_execute ? "var(--green-dim)" : "transparent",
                    borderColor: form.auto_execute ? "rgba(0,255,136,0.4)" : "var(--border)",
                    color: form.auto_execute ? "var(--green)" : "var(--muted)",
                  }}>
                  ⚡ AUTO-EXECUTE
                </button>
                <button type="button"
                  onClick={() => setForm(f => ({ ...f, auto_execute: false }))}
                  style={{
                    flex: 1, padding: 11, fontFamily: "var(--font)", fontSize: 11,
                    letterSpacing: 1, cursor: "pointer", border: "1px solid",
                    background: !form.auto_execute ? "rgba(255,208,96,0.1)" : "transparent",
                    borderColor: !form.auto_execute ? "rgba(255,208,96,0.4)" : "var(--border)",
                    color: !form.auto_execute ? "var(--yellow)" : "var(--muted)",
                  }}>
                  🔔 NOTIFY ONLY
                </button>
              </div>
            </div>

            <button className="auth-btn" disabled={!form.leader_id || followMutation.isPending}
              onClick={() => followMutation.mutate()} style={{ marginTop: 4 }}>
              {followMutation.isPending ? "FOLLOWING..." : "START COPYING →"}
            </button>
          </div>
        )}

        {!following?.length && !showForm && (
          <div className="empty-state">Not following any leaders yet.</div>
        )}

        {following?.map((f: any) => (
          <div key={f.id} className="broker-item" style={{ padding: "14px 20px" }}>
            <div>
              <div className="broker-name">{f.leader_username}</div>
              <div className="broker-id">
                {f.qty_multiplier}x qty ·{" "}
                {f.auto_execute ? "Auto-execute" : "Notify only"}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="connect-btn"
                onClick={() => toggleMutation.mutate({ id: f.id, is_active: !f.is_active })}
                style={{ padding: "6px 12px", fontSize: 10 }}>
                {f.is_active ? "PAUSE" : "RESUME"}
              </button>
              <button className="exit-btn"
                onClick={() => unfollowMutation.mutate(f.id)}>
                UNFOLLOW
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="info-box">
        <div className="info-icon">ℹ</div>
        <div>
          <div className="info-title">HOW COPY TRADING WORKS</div>
          <div className="info-body">
            When your leader's TradingView alert fires, the signal hits your server instantly.
            In auto-execute mode, your broker places the order automatically.
            In notify-only mode, you get a live notification and can decide manually.
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── HISTORY TAB ─────────────────────────────────────────────────────────── */
function HistoryTab() {
  const { data: history, isLoading } = useQuery({
    queryKey: ["signal-history"],
    queryFn: () => api.get("/signals/history").then(r => r.data),
  });

  if (isLoading) return <Spinner />;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">SIGNAL HISTORY</span>
        <span className="card-badge">{history?.length ?? 0} signals</span>
      </div>
      {(!history || history.length === 0) ? (
        <div className="empty-state">No signals sent yet. Set up your webhook to get started.</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>{["TIME","SYMBOL","DIRECTION","QTY","PRICE","TAG","STATUS"].map(h => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {history.map((s: any) => (
              <tr key={s.id}>
                <td style={{ color: "var(--muted)", fontSize: 11 }}>
                  {new Date(s.created_at).toLocaleTimeString()}
                </td>
                <td className="symbol">{s.symbol}</td>
                <td><span className={`badge ${s.direction === "BUY" ? "badge-green" : "badge-red"}`}>{s.direction}</span></td>
                <td>{s.quantity ?? "—"}</td>
                <td>{s.price ? `₹${s.price.toLocaleString()}` : "—"}</td>
                <td style={{ color: "var(--muted)", fontSize: 11 }}>{s.strategy_tag ?? "—"}</td>
                <td><span className={`badge ${s.status === "done" ? "badge-green" : s.status === "failed" ? "badge-red" : "badge-yellow"}`}>
                  {s.status.toUpperCase()}
                </span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Spinner() {
  return <div style={{ color: "var(--muted)", fontSize: 12, padding: 20 }}>Loading...</div>;
}
