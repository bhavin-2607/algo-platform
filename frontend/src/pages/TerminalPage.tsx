import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

// ── Types ─────────────────────────────────────────────────────────────────────
interface TerminalRow {
  id: string;
  symbol: string;
  exchange: string;
  strategy_label: string;
  quantity: number;
  trade_mode: string;
  target_pct: number | null;
  sl_pct: number | null;
  trailing_sl: boolean;
  trail_pct: number | null;
  auto_execute: boolean;
  is_active: boolean;
  status: string;
  // Live data
  ltp: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  oi: number | null;
  bp1: number | null;
  sp1: number | null;
  signal: string;
  entry_price: number | null;
  current_sl: number | null;
  current_target: number | null;
  pnl: number | null;
  // Admin only
  entry_formula?: string;
  exit_formula?: string;
}

export default function TerminalPage() {
  const qc = useQueryClient();
  const { accessToken, user } = useAuthStore();
  const isAdmin = user?.role === "admin";

  // Live data from WebSocket — overrides REST poll
  const [liveData, setLiveData] = useState<Record<string, Partial<TerminalRow>>>({});
  const wsRef = useRef<WebSocket | null>(null);

  const { data: rows, isLoading } = useQuery({
    queryKey: ["terminal-rows"],
    queryFn: () => api.get("/terminal/rows").then(r => r.data as TerminalRow[]),
    refetchInterval: 5_000,
  });

  const { data: termStatus } = useQuery({
    queryKey: ["terminal-status"],
    queryFn: () => api.get("/terminal/status").then(r => r.data),
    refetchInterval: 3_000,
  });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  // WebSocket for live tick data
  useEffect(() => {
    if (!accessToken) return;
    const wsBase = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000").replace("http", "ws");
    const ws = new WebSocket(`${wsBase}/api/ws/feed?token=${accessToken}`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.row_id) {
          setLiveData(prev => ({ ...prev, [data.row_id]: data }));
        }
      } catch {}
    };
    return () => ws.close();
  }, [accessToken]);

  const startMutation = useMutation({
    mutationFn: () => api.post("/terminal/start"),
    onSuccess: () => { toast.success("Terminal started"); qc.invalidateQueries({ queryKey: ["terminal-status"] }); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed to start"),
  });

  const stopMutation = useMutation({
    mutationFn: () => api.post("/terminal/stop"),
    onSuccess: () => { toast.success("Terminal stopped"); qc.invalidateQueries({ queryKey: ["terminal-status"] }); },
  });

  const exitMutation = useMutation({
    mutationFn: (id: string) => api.post(`/terminal/rows/${id}/exit`),
    onSuccess: () => { toast.success("Exit order sent"); qc.invalidateQueries({ queryKey: ["terminal-rows"] }); },
    onError: () => toast.error("No active position on this row"),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: any) => api.patch(`/terminal/rows/${id}/activate`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["terminal-rows"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/terminal/rows/${id}`),
    onSuccess: () => { toast.success("Row removed"); qc.invalidateQueries({ queryKey: ["terminal-rows"] }); },
  });

  const isRunning = termStatus?.running;

  // Merge REST data with live WebSocket updates
  const mergedRows: TerminalRow[] = (rows ?? []).map(r => ({
    ...r,
    ...(liveData[r.id] ?? {}),
  }));

  const [showAddForm, setShowAddForm] = useState(false);
  const [editingRow,  setEditingRow]  = useState<TerminalRow | null>(null);

  return (
    <Layout>
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">TRADE TERMINAL</h1>
          <p className="page-sub">Live multi-symbol trading — replaces Excel terminal</p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <div className={`market-status${isRunning ? "" : " stopped"}`}
            style={!isRunning ? { color: "var(--muted)" } : {}}>
            <div className="market-dot" style={!isRunning ? { background: "var(--muted)", boxShadow: "none" } : {}} />
            <span>{isRunning ? "TERMINAL LIVE" : "TERMINAL STOPPED"}</span>
          </div>
          {isRunning
            ? <button onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending}
                style={{ padding: "8px 16px", background: "rgba(255,68,102,0.1)", border: "1px solid rgba(255,68,102,0.4)",
                  color: "var(--red)", fontFamily: "var(--font)", fontSize: 11, cursor: "pointer", letterSpacing: 1 }}>
                ⏹ STOP
              </button>
            : <button onClick={() => startMutation.mutate()} disabled={startMutation.isPending}
                style={{ padding: "8px 16px", background: "var(--green-dim)", border: "1px solid rgba(0,255,136,0.4)",
                  color: "var(--green)", fontFamily: "var(--font)", fontSize: 11, cursor: "pointer", letterSpacing: 1 }}>
                {startMutation.isPending ? "STARTING..." : "▶ START"}
              </button>
          }
          <button className="connect-btn" onClick={() => { setEditingRow(null); setShowAddForm(v => !v); }}>
            {showAddForm ? "✕ CANCEL" : "+ ADD SYMBOL"}
          </button>
        </div>
      </div>

      {/* Add/Edit form */}
      {(showAddForm || editingRow) && (
        <AddRowForm
          brokers={brokers ?? []}
          isAdmin={isAdmin}
          initial={editingRow}
          onSaved={() => { setShowAddForm(false); setEditingRow(null); qc.invalidateQueries({ queryKey: ["terminal-rows"] }); }}
          onCancel={() => { setShowAddForm(false); setEditingRow(null); }}
        />
      )}

      {/* Terminal table */}
      <div className="card" style={{ overflowX: "auto" }}>
        <div className="card-header">
          <span className="card-title">SYMBOL WATCHLIST</span>
          <span className="card-badge">{mergedRows.length} symbols</span>
        </div>

        {isLoading && <div style={{ padding: "24px 20px", color: "var(--muted)", fontSize: 12 }}>Loading...</div>}

        {!isLoading && mergedRows.length === 0 && (
          <div className="empty-state">
            No symbols added. Click <strong>+ ADD SYMBOL</strong> to start.
          </div>
        )}

        {mergedRows.length > 0 && (
          <table className="data-table" style={{ minWidth: 1100 }}>
            <thead>
              <tr>
                <th style={{ width: 32 }}>ON</th>
                <th>SYMBOL</th>
                <th>STRATEGY</th>
                <th>LTP</th>
                <th>OPEN</th>
                <th>HIGH</th>
                <th>LOW</th>
                <th>VOLUME</th>
                <th>SIGNAL</th>
                <th>ENTRY ₹</th>
                <th>TARGET</th>
                <th>SL</th>
                <th>P&L</th>
                <th>STATUS</th>
                <th>MODE</th>
                <th style={{ width: 120 }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {mergedRows.map(row => (
                <TerminalTableRow
                  key={row.id}
                  row={row}
                  isAdmin={isAdmin}
                  onToggle={() => toggleMutation.mutate({ id: row.id, is_active: !row.is_active })}
                  onExit={() => exitMutation.mutate(row.id)}
                  onEdit={() => { setEditingRow(row); setShowAddForm(false); }}
                  onDelete={() => deleteMutation.mutate(row.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Summary footer */}
      {mergedRows.length > 0 && (
        <div className="stats-grid" style={{ marginTop: 16 }}>
          <SumCard label="ACTIVE ROWS"
            value={mergedRows.filter(r => r.is_active).length}
            color={mergedRows.some(r => r.is_active) ? "green" : undefined} />
          <SumCard label="IN POSITION"
            value={mergedRows.filter(r => r.status === "active").length} />
          <SumCard label="TOTAL P&L TODAY"
            value={`₹${mergedRows.reduce((s, r) => s + (r.pnl ?? 0), 0).toLocaleString()}`}
            color={mergedRows.reduce((s, r) => s + (r.pnl ?? 0), 0) >= 0 ? "green" : "red"} />
          <SumCard label="BUY SIGNALS"
            value={mergedRows.filter(r => r.signal === "BUY").length}
            color={mergedRows.some(r => r.signal === "BUY") ? "green" : undefined} />
        </div>
      )}
    </Layout>
  );
}

/* ── Terminal Table Row ────────────────────────────────────────────────────── */
function TerminalTableRow({ row, isAdmin, onToggle, onExit, onEdit, onDelete }: {
  row: TerminalRow;
  isAdmin: boolean;
  onToggle: () => void;
  onExit: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const pnl     = row.pnl ?? 0;
  const inPos   = row.status === "active";
  const signal  = row.signal ?? "—";

  return (
    <tr style={{ background: inPos ? "rgba(0,255,136,0.02)" : undefined }}>
      {/* Toggle */}
      <td>
        <div onClick={onToggle} style={{
          width: 24, height: 24, borderRadius: "50%", cursor: "pointer",
          border: `2px solid ${row.is_active ? "var(--green)" : "var(--border)"}`,
          background: row.is_active ? "var(--green)" : "transparent",
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "all 0.2s",
        }}>
          {row.is_active && <span style={{ color: "var(--bg)", fontSize: 10, fontWeight: 700 }}>✓</span>}
        </div>
      </td>

      <td className="symbol">{row.symbol}<br /><span style={{ fontSize: 9, color: "var(--muted)" }}>{row.exchange}</span></td>
      <td style={{ fontSize: 11, color: "var(--muted)" }}>{row.strategy_label}</td>

      {/* Live prices */}
      <td style={{ fontWeight: 700, fontSize: 13 }}>{row.ltp ? `₹${row.ltp.toLocaleString()}` : "—"}</td>
      <td style={{ fontSize: 11, color: "var(--muted)" }}>{row.open ? `₹${row.open.toLocaleString()}` : "—"}</td>
      <td style={{ fontSize: 11, color: "var(--green)" }}>{row.high ? `₹${row.high.toLocaleString()}` : "—"}</td>
      <td style={{ fontSize: 11, color: "var(--red)" }}>{row.low ? `₹${row.low.toLocaleString()}` : "—"}</td>
      <td style={{ fontSize: 11, color: "var(--muted)" }}>{row.volume ? `${(row.volume / 100000).toFixed(1)}L` : "—"}</td>

      {/* Signal */}
      <td>
        <span className={`badge ${
          signal === "BUY"  ? "badge-green" :
          signal === "SELL" ? "badge-red"   :
          signal === "EXIT" ? "badge-yellow" : "badge-gray"
        }`} style={{ minWidth: 50, textAlign: "center" }}>
          {signal}
        </span>
      </td>

      {/* Position */}
      <td style={{ color: inPos ? "var(--text)" : "var(--muted)", fontSize: 11 }}>
        {row.entry_price ? `₹${row.entry_price.toLocaleString()}` : "—"}
      </td>
      <td style={{ color: "var(--green)", fontSize: 11 }}>
        {row.current_target ? `₹${row.current_target.toLocaleString()}` : "—"}
      </td>
      <td style={{ color: "var(--red)", fontSize: 11 }}>
        {row.current_sl ? `₹${row.current_sl.toLocaleString()}` : "—"}
      </td>

      {/* P&L */}
      <td className={pnl >= 0 ? "pnl-pos" : "pnl-neg"} style={{ fontWeight: 700 }}>
        {pnl !== 0 ? `${pnl >= 0 ? "+" : ""}₹${pnl.toLocaleString()}` : "—"}
      </td>

      {/* Status */}
      <td>
        <span className={`badge ${
          row.status === "active"        ? "badge-green" :
          row.status === "entry_pending" ? "badge-yellow" :
          row.status === "exit_pending"  ? "badge-yellow" :
          row.status === "watching"      ? "badge-gray" : "badge-gray"
        }`}>
          {row.status.toUpperCase().replace("_", " ")}
        </span>
      </td>

      {/* Mode */}
      <td>
        <span className={`badge ${row.trade_mode === "REAL" ? "badge-red" : "badge-yellow"}`}>
          {row.trade_mode}
        </span>
      </td>

      {/* Actions */}
      <td>
        <div style={{ display: "flex", gap: 4 }}>
          {inPos && (
            <button className="exit-btn" style={{ color: "var(--red)", borderColor: "rgba(255,68,102,0.4)", padding: "3px 8px", fontSize: 10 }}
              onClick={onExit}>EXIT</button>
          )}
          <button className="exit-btn" style={{ padding: "3px 8px", fontSize: 10 }} onClick={onEdit}>EDIT</button>
          {!inPos && (
            <button className="exit-btn" style={{ padding: "3px 8px", fontSize: 10, color: "var(--muted)" }} onClick={onDelete}>✕</button>
          )}
        </div>
      </td>
    </tr>
  );
}

/* ── Add/Edit Row Form ────────────────────────────────────────────────────── */
function AddRowForm({ brokers, isAdmin, initial, onSaved, onCancel }: any) {
  const [form, setForm] = useState({
    symbol:         initial?.symbol         ?? "",
    exchange:       initial?.exchange       ?? "NSE",
    token:          initial?.token          ?? "",
    strategy_label: initial?.strategy_label ?? "",
    entry_formula:  initial?.entry_formula  ?? "",
    exit_formula:   initial?.exit_formula   ?? "",
    quantity:       initial?.quantity       ?? 1,
    product_type:   initial?.product_type   ?? "MIS",
    order_type:     initial?.order_type     ?? "MARKET",
    trade_mode:     initial?.trade_mode     ?? "PAPER",
    target_pct:     initial?.target_pct     ?? "",
    sl_pct:         initial?.sl_pct         ?? "",
    trailing_sl:    initial?.trailing_sl    ?? false,
    trail_pct:      initial?.trail_pct      ?? "",
    auto_execute:   initial?.auto_execute   ?? true,
    broker_account_id: initial?.broker_account_id ?? "",
  });

  const { data: instruments } = useQuery({
    queryKey: ["terminal-instruments", form.symbol],
    queryFn: () => api.get(`/terminal/instruments?q=${form.symbol}`).then(r => r.data),
    enabled: form.symbol.length >= 2,
  });

  const set = (k: string) => (e: any) => setForm(f => ({ ...f, [k]: e.target?.value ?? e }));

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        ...form,
        quantity:  parseInt(String(form.quantity)),
        target_pct: form.target_pct ? parseFloat(String(form.target_pct)) : null,
        sl_pct:     form.sl_pct     ? parseFloat(String(form.sl_pct))     : null,
        trail_pct:  form.trail_pct  ? parseFloat(String(form.trail_pct))  : null,
        broker_account_id: form.broker_account_id || null,
        token: form.token || null,
      };
      return initial
        ? api.put(`/terminal/rows/${initial.id}`, payload)
        : api.post("/terminal/rows", payload);
    },
    onSuccess: () => { toast.success(initial ? "Row updated" : "Symbol added"); onSaved(); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Save failed"),
  });

  function pickInstrument(inst: any) {
    setForm(f => ({ ...f, symbol: inst.symbol, exchange: inst.exchange, token: inst.token }));
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-header">
        <span className="card-title">{initial ? "EDIT ROW" : "ADD SYMBOL TO TERMINAL"}</span>
      </div>
      <div style={{ padding: "20px 20px 8px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
          {/* Symbol with autocomplete */}
          <div className="field">
            <label className="field-label">SYMBOL</label>
            <input className="field-input" value={form.symbol}
              onChange={set("symbol")} placeholder="e.g. RELIANCE" />
            {instruments?.length > 0 && form.symbol && (
              <div style={{ border: "1px solid var(--border)", background: "var(--surface)", marginTop: 2 }}>
                {instruments.slice(0, 6).map((inst: any) => (
                  <div key={inst.symbol} onClick={() => pickInstrument(inst)}
                    style={{ padding: "8px 12px", cursor: "pointer", fontSize: 12, borderBottom: "1px solid var(--border)" }}
                    onMouseEnter={e => (e.currentTarget.style.background = "var(--green-dim)")}
                    onMouseLeave={e => (e.currentTarget.style.background = "")}>
                    <span style={{ color: "var(--green)" }}>{inst.symbol}</span>
                    <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: 11 }}>{inst.exchange}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <TInput label="STRATEGY LABEL" value={form.strategy_label} onChange={set("strategy_label")} placeholder="My Strategy" />
          <TInput label="QTY" value={form.quantity} onChange={set("quantity")} type="number" />
          <div className="field">
            <label className="field-label">PRODUCT</label>
            <select className="field-input" value={form.product_type} onChange={set("product_type")}
              style={{ background: "rgba(0,255,136,0.04)", color: "var(--text)", fontFamily: "var(--font)" }}>
              <option>MIS</option><option>CNC</option><option>NRML</option>
            </select>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
          <TInput label="TARGET %" value={form.target_pct} onChange={set("target_pct")} type="number" placeholder="2.0" />
          <TInput label="STOP LOSS %" value={form.sl_pct} onChange={set("sl_pct")} type="number" placeholder="1.0" />
          <div className="field">
            <label className="field-label">TRAILING SL</label>
            <div style={{ display: "flex" }}>
              {["ON","OFF"].map((v,i) => (
                <button key={v} type="button"
                  onClick={() => setForm(f => ({ ...f, trailing_sl: v === "ON" }))}
                  style={{
                    flex: 1, padding: 10, fontFamily: "var(--font)", fontSize: 11, cursor: "pointer",
                    borderRight: i === 0 ? "none" : undefined, border: "1px solid",
                    background: (form.trailing_sl && v==="ON") || (!form.trailing_sl && v==="OFF") ? "var(--green-dim)" : "transparent",
                    borderColor: (form.trailing_sl && v==="ON") || (!form.trailing_sl && v==="OFF") ? "rgba(0,255,136,0.4)" : "var(--border)",
                    color: (form.trailing_sl && v==="ON") || (!form.trailing_sl && v==="OFF") ? "var(--green)" : "var(--muted)",
                  }}>{v}</button>
              ))}
            </div>
          </div>
          {form.trailing_sl && <TInput label="TRAIL %" value={form.trail_pct} onChange={set("trail_pct")} type="number" placeholder="0.5" />}
        </div>

        {/* Hidden formulas — admin only */}
        {isAdmin && (
          <>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "var(--yellow)", margin: "4px 0 8px" }}>
              🔒 STRATEGY FORMULAS (ADMIN ONLY — hidden from users)
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
              <TInput label="ENTRY FORMULA" value={form.entry_formula} onChange={set("entry_formula")}
                placeholder="e.g. ma(9) > ma(21) AND rsi(14) < 70" />
              <TInput label="EXIT FORMULA" value={form.exit_formula} onChange={set("exit_formula")}
                placeholder="e.g. ma(9) < ma(21) OR rsi(14) > 80" />
            </div>
          </>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 4 }}>
          <div className="field">
            <label className="field-label">TRADE MODE</label>
            <div style={{ display: "flex" }}>
              {["PAPER","REAL"].map((v, i) => (
                <button key={v} type="button"
                  onClick={() => setForm(f => ({ ...f, trade_mode: v }))}
                  style={{
                    flex: 1, padding: 10, fontFamily: "var(--font)", fontSize: 11, cursor: "pointer",
                    borderRight: i === 0 ? "none" : undefined, border: "1px solid",
                    background: form.trade_mode === v ? (v==="REAL" ? "rgba(255,68,102,0.1)" : "rgba(255,208,96,0.1)") : "transparent",
                    borderColor: form.trade_mode === v ? (v==="REAL" ? "rgba(255,68,102,0.4)" : "rgba(255,208,96,0.4)") : "var(--border)",
                    color: form.trade_mode === v ? (v==="REAL" ? "var(--red)" : "var(--yellow)") : "var(--muted)",
                  }}>{v}</button>
              ))}
            </div>
          </div>
          <div className="field">
            <label className="field-label">BROKER</label>
            <select className="field-input" value={form.broker_account_id} onChange={set("broker_account_id")}
              style={{ background: "rgba(0,255,136,0.04)", color: "var(--text)", fontFamily: "var(--font)" }}>
              <option value="">Select broker</option>
              {brokers.map((b: any) => (
                <option key={b.id} value={b.id}>{b.broker.toUpperCase()} — {b.paper_trading ? "Paper" : "Live"}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label">EXECUTION</label>
            <div style={{ display: "flex" }}>
              {["AUTO","MANUAL"].map((v, i) => (
                <button key={v} type="button"
                  onClick={() => setForm(f => ({ ...f, auto_execute: v === "AUTO" }))}
                  style={{
                    flex: 1, padding: 10, fontFamily: "var(--font)", fontSize: 11, cursor: "pointer",
                    borderRight: i === 0 ? "none" : undefined, border: "1px solid",
                    background: (form.auto_execute && v==="AUTO") || (!form.auto_execute && v==="MANUAL") ? "var(--green-dim)" : "transparent",
                    borderColor: (form.auto_execute && v==="AUTO") || (!form.auto_execute && v==="MANUAL") ? "rgba(0,255,136,0.4)" : "var(--border)",
                    color: (form.auto_execute && v==="AUTO") || (!form.auto_execute && v==="MANUAL") ? "var(--green)" : "var(--muted)",
                  }}>{v}</button>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, marginTop: 16, paddingBottom: 8 }}>
          <button className={`auth-btn${saveMutation.isPending ? " loading" : ""}`}
            onClick={() => saveMutation.mutate()} disabled={!form.symbol || saveMutation.isPending}
            style={{ maxWidth: 220 }}>
            {saveMutation.isPending ? "SAVING..." : initial ? "UPDATE ROW →" : "ADD TO TERMINAL →"}
          </button>
          <button className="exit-btn" onClick={onCancel} style={{ padding: "12px 20px" }}>CANCEL</button>
        </div>
      </div>
    </div>
  );
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function TInput({ label, value, onChange, type = "text", placeholder }: any) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input className="field-input" type={type} value={value ?? ""}
        onChange={onChange} placeholder={placeholder} />
    </div>
  );
}

function SumCard({ label, value, color }: any) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{
        color: color === "green" ? "var(--green)" : color === "red" ? "var(--red)" : "var(--text)"
      }}>{value}</div>
    </div>
  );
}
