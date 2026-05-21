import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { brokerApi } from "@/utils/api";
import toast from "react-hot-toast";

const MOCK_ORDERS = [
  { id: "ORD001", symbol: "RELIANCE",      side: "BUY",  qty: 50,  price: 2840.50, status: "COMPLETE",  time: "09:17:32" },
  { id: "ORD002", symbol: "TCS",           side: "BUY",  qty: 25,  price: 3920.00, status: "COMPLETE",  time: "09:22:10" },
  { id: "ORD003", symbol: "INFY",          side: "SELL", qty: 100, price: 1540.00, status: "CANCELLED", time: "10:05:44" },
  { id: "ORD004", symbol: "NIFTY25JUNFUT", side: "BUY",  qty: 2,   price: 24850,   status: "OPEN",      time: "10:31:02" },
];

const BROKER_OPTIONS = [
  { value: "dhan",      label: "Dhan / DhanHQ",      desc: "Free API · Simple token auth · Recommended" },
  { value: "shoonya",   label: "Shoonya / Finvasia",  desc: "Free API · Requires IP whitelisting" },
  { value: "angel_one", label: "Angel One",           desc: "Coming soon", disabled: true },
  { value: "upstox",    label: "Upstox",              desc: "Coming soon", disabled: true },
];

export default function TradingPage() {
  const [tab, setTab] = useState<"orders" | "brokers">("orders");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">TRADING</h1>
          <p className="page-sub">Order management & broker connections</p>
        </div>
        <div className="tab-switcher">
          <button className={`tab-btn${tab === "orders"  ? " active" : ""}`} onClick={() => setTab("orders")}>ORDER BOOK</button>
          <button className={`tab-btn${tab === "brokers" ? " active" : ""}`} onClick={() => setTab("brokers")}>BROKERS</button>
        </div>
      </div>

      {tab === "orders"  && <OrdersTab />}
      {tab === "brokers" && <BrokersTab />}
    </Layout>
  );
}

/* ── ORDER BOOK ──────────────────────────────────────────── */
function OrdersTab() {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">TODAY'S ORDERS</span>
        <span className="card-badge">{MOCK_ORDERS.length} orders</span>
      </div>
      <table className="data-table">
        <thead>
          <tr>{["ORDER ID","SYMBOL","SIDE","QTY","PRICE","STATUS","TIME"].map(h => <th key={h}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {MOCK_ORDERS.map((o) => (
            <tr key={o.id}>
              <td style={{ color: "#4a5568", fontSize: 11 }}>{o.id}</td>
              <td className="symbol">{o.symbol}</td>
              <td><span className={`badge ${o.side === "BUY" ? "badge-green" : "badge-red"}`}>{o.side}</span></td>
              <td>{o.qty}</td>
              <td>₹{o.price.toLocaleString()}</td>
              <td>
                <span className={`badge ${
                  o.status === "COMPLETE" ? "badge-green" :
                  o.status === "OPEN"     ? "badge-yellow" : "badge-gray"
                }`}>{o.status}</span>
              </td>
              <td style={{ color: "#4a5568", fontSize: 11 }}>{o.time}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── BROKERS ─────────────────────────────────────────────── */
function BrokersTab() {
  const qc = useQueryClient();
  const { data: brokers, isLoading } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => brokerApi.list(),
  });

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    broker: "shoonya",
    client_id: "",
    paper_trading: true,
  });

  const connectMutation = useMutation({
    mutationFn: () => brokerApi.connect(form),
    onSuccess: () => {
      toast.success(`${form.broker.toUpperCase()} linked in ${form.paper_trading ? "paper" : "live"} mode`);
      qc.invalidateQueries({ queryKey: ["brokers"] });
      setShowForm(false);
      setForm({ broker: "shoonya", client_id: "", paper_trading: true });
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Connection failed"),
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => brokerApi.activate(id),
    onSuccess: () => {
      toast.success("Broker activated successfully");
      qc.invalidateQueries({ queryKey: ["brokers"] });
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Activation failed"),
  });

  const disconnectMutation = useMutation({
    mutationFn: (id: string) => brokerApi.disconnect(id),
    onSuccess: () => {
      toast.success("Broker account removed");
      qc.invalidateQueries({ queryKey: ["brokers"] });
    },
    onError: () => toast.error("Failed to remove broker"),
  });

  const set = (k: string) => (v: any) => setForm(f => ({ ...f, [k]: v }));

  const connected: any[] = brokers?.data ?? [];

  return (
    <div>
      {/* Connected brokers */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title">CONNECTED BROKERS</span>
          <button className="connect-btn" onClick={() => setShowForm(v => !v)}>
            {showForm ? "✕ CANCEL" : "+ ADD BROKER"}
          </button>
        </div>

        {isLoading && <div style={{ padding: "24px 20px", color: "var(--muted)", fontSize: 12 }}>Loading...</div>}

        {!isLoading && connected.length === 0 && !showForm && (
          <div className="empty-state">
            No brokers connected yet. Click <strong>+ ADD BROKER</strong> to get started.
          </div>
        )}

        {connected.map((b: any) => (
          <div key={b.id} className="broker-item" style={{ padding: "16px 20px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{
                width: 36, height: 36, background: "var(--green-dim)",
                border: "1px solid var(--border)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, fontWeight: 700, color: "var(--green)",
              }}>
                {b.broker[0].toUpperCase()}
              </div>
              <div>
                <div className="broker-name">{b.broker.toUpperCase().replace("_"," ")}</div>
                <div className="broker-id">Client ID: {b.client_id}</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className={`badge ${b.paper_trading ? "badge-yellow" : "badge-green"}`}>
                {b.paper_trading ? "PAPER" : "LIVE"}
              </span>
              <span className={`badge ${b.is_active ? "badge-green" : "badge-gray"}`}>
                {b.is_active ? "ACTIVE" : "INACTIVE"}
              </span>
              {!b.is_active && (
                <button
                  className="connect-btn"
                  style={{ padding: "5px 12px", fontSize: 10 }}
                  onClick={() => activateMutation.mutate(b.id)}
                  disabled={activateMutation.isPending}
                >
                  {activateMutation.isPending ? "..." : "⚡ ACTIVATE"}
                </button>
              )}
              <button
                className="exit-btn"
                onClick={() => disconnectMutation.mutate(b.id)}
                style={{ marginLeft: 4 }}
              >
                REMOVE
              </button>
            </div>
          </div>
        ))}

        {/* Inline connection form */}
        {showForm && (
          <div style={{ padding: "20px 20px 24px", borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: 11, letterSpacing: 2, color: "var(--green)", marginBottom: 20 }}>
              NEW BROKER CONNECTION
            </div>

            {/* Broker selector */}
            <div className="field">
              <label className="field-label">SELECT BROKER</label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                {BROKER_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    disabled={opt.disabled}
                    onClick={() => !opt.disabled && set("broker")(opt.value)}
                    style={{
                      padding: "12px 14px", textAlign: "left",
                      background: form.broker === opt.value ? "var(--green-dim)" : "transparent",
                      border: `1px solid ${form.broker === opt.value ? "rgba(0,255,136,0.4)" : "var(--border)"}`,
                      color: opt.disabled ? "var(--muted)" : form.broker === opt.value ? "var(--green)" : "var(--text)",
                      cursor: opt.disabled ? "not-allowed" : "pointer",
                      opacity: opt.disabled ? 0.4 : 1,
                      fontFamily: "var(--font)",
                      transition: "all 0.15s",
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 3 }}>{opt.label}</div>
                    <div style={{ fontSize: 10, color: "var(--muted)" }}>{opt.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Client ID */}
            <div className="field">
              <label className="field-label">CLIENT ID</label>
              <input
                className="field-input"
                type="text"
                placeholder="Your broker client ID (e.g. FA12345)"
                value={form.client_id}
                onChange={(e) => set("client_id")(e.target.value)}
              />
              <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
                Find this in your Shoonya / Finvasia account dashboard
              </div>
            </div>

            {/* Paper / Live toggle */}
            <div className="field">
              <label className="field-label">TRADING MODE</label>
              <div style={{ display: "flex", gap: 0, marginTop: 4 }}>
                <button
                  type="button"
                  onClick={() => set("paper_trading")(true)}
                  style={{
                    flex: 1, padding: "11px",
                    background: form.paper_trading ? "rgba(255,208,96,0.15)" : "transparent",
                    border: `1px solid ${form.paper_trading ? "rgba(255,208,96,0.4)" : "var(--border)"}`,
                    borderRight: "none",
                    color: form.paper_trading ? "var(--yellow)" : "var(--muted)",
                    fontFamily: "var(--font)", fontSize: 11, letterSpacing: 1, cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                >
                  ◎ PAPER (Simulated)
                </button>
                <button
                  type="button"
                  onClick={() => set("paper_trading")(false)}
                  style={{
                    flex: 1, padding: "11px",
                    background: !form.paper_trading ? "rgba(255,68,102,0.1)" : "transparent",
                    border: `1px solid ${!form.paper_trading ? "rgba(255,68,102,0.4)" : "var(--border)"}`,
                    color: !form.paper_trading ? "var(--red)" : "var(--muted)",
                    fontFamily: "var(--font)", fontSize: 11, letterSpacing: 1, cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                >
                  ● LIVE (Real money)
                </button>
              </div>
            </div>

            {!form.paper_trading && (
              <div className="info-box" style={{ marginBottom: 16 }}>
                <div className="info-icon">⚠</div>
                <div>
                  <div className="info-title" style={{ color: "var(--red)" }}>LIVE MODE WARNING</div>
                  <div className="info-body">
                    Real orders will be placed with real money. Ensure your Shoonya credentials
                    are configured in <code>.env</code> before activating.
                  </div>
                </div>
              </div>
            )}

            <button
              className="auth-btn"
              disabled={!form.client_id.trim() || connectMutation.isPending}
              onClick={() => connectMutation.mutate()}
              style={{ marginTop: 4 }}
            >
              {connectMutation.isPending ? "CONNECTING..." : "CONNECT BROKER →"}
            </button>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="info-box">
        <div className="info-icon">ℹ</div>
        <div>
          <div className="info-title">ABOUT PAPER TRADING</div>
          <div className="info-body">
            Paper mode simulates all orders without touching real capital. Use it to validate
            strategies before going live. Switch to live mode only after thorough paper testing.
          </div>
        </div>
      </div>
    </div>
  );
}
