import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api, brokerApi } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

const BROKER_OPTIONS = [
  { value: "dhan", label: "Dhan / DhanHQ",
    desc: "Free Trading API · Data API available · Recommended" },
];

function exportToCsv(filename: string, rows: Record<string, any>[]) {
  if (!rows || !rows.length) return;
  const separator = ",";
  const keys = Object.keys(rows[0]);
  const csvContent =
    keys.join(separator) +
    "\n" +
    rows.map(row => {
      return keys.map(k => {
        let val = row[k] === null || row[k] === undefined ? "" : row[k];
        val = String(val).replace(/"/g, '""');
        if (String(val).search(/("|,|\n)/g) >= 0) {
          val = `"${val}"`;
        }
        return val;
      }).join(separator);
    }).join("\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export default function TradingPage() {
  const { data: orderbook, isLoading: obLoading } = useQuery({
    queryKey: ["orderbook"],
    queryFn: () => api.get("/terminal/orderbook").then(r => r.data),
    refetchInterval: 10000,
  });
  const { data: positions, isLoading: posLoading } = useQuery({
    queryKey: ["dhan-positions"],
    queryFn: () => api.get("/terminal/positions").then(r => r.data),
    refetchInterval: 10000,
  });
  const { data: tradeHistory, isLoading: thLoading } = useQuery({
    queryKey: ["dhan-trade-history"],
    queryFn: () => api.get("/terminal/trade-history").then(r => r.data),
    refetchInterval: 10000,
  });
  const qc = useQueryClient();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<"all" | "positions" | "orders" | "history">("all");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ broker:"dhan", client_id:"", access_token:"", paper_trading:true });

  const guardPositionMutation = useMutation({
    mutationFn: (p: any) =>
      api.post("/terminal/algo-rows/import-position", {
        symbol: p.symbol,
        segment: p.segment || (p.exchange === "MCX" ? "MCX_COMM" : p.product_type === "CNC" ? "NSE_EQ" : "NSE_FNO"),
        exchange: p.exchange || "NSE",
        security_id: p.security_id || p.securityId,
        quantity: Math.abs(Number(p.net_qty) || 1),
        buy_price: Number(p.buy_avg || p.entry_price || p.cost_price || 0),
        target_type: "T1",
      }),
    onSuccess: (res: any) => {
      toast.success(`Position ${res.data?.symbol || ""} imported into Algo Window in SELL_ONLY mode`);
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || "Failed to guard position with algo"),
  });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  const connectMutation = useMutation({
    mutationFn: () => api.post("/brokers", {
      broker: form.broker, client_id: form.client_id || "DHAN_PAPER",
      paper_trading: form.paper_trading,
    }).then(async (res) => {
      // If live broker with token provided, save credentials too
      if (!form.paper_trading && form.access_token && form.client_id) {
        await api.post("/settings/dhan-credentials", {
          client_id: form.client_id,
          access_token: form.access_token,
        });
      }
      return res;
    }),
    onSuccess: () => {
      toast.success("Broker account added");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
      setShowForm(false);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed"),
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => brokerApi.activate(id),
    onSuccess: () => {
      toast.success("Broker activated");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Activation failed"),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => brokerApi.disconnect(id),
    onSuccess: () => {
      toast.success("Removed");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
    },
  });

  const visibleBrokers = (brokers ?? []).filter((b: any) => b.broker === "dhan" || b.broker === "paper");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">POSITIONS & ORDERS</h1>
          <p className="page-sub">Live Dhan positions, execution orderbook, and trade history</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div className="tab-switcher">
            <button
              className={`tab-btn${tab === "all" ? " active" : ""}`}
              onClick={() => setTab("all")}
            >
              ALL
            </button>
            <button
              className={`tab-btn${tab === "positions" ? " active" : ""}`}
              onClick={() => setTab("positions")}
            >
              POSITIONS ({positions?.length ?? 0})
            </button>
            <button
              className={`tab-btn${tab === "orders" ? " active" : ""}`}
              onClick={() => setTab("orders")}
            >
              ORDER BOOK ({orderbook?.length ?? 0})
            </button>
            <button
              className={`tab-btn${tab === "history" ? " active" : ""}`}
              onClick={() => setTab("history")}
            >
              TRADE HISTORY ({tradeHistory?.trades?.length ?? 0})
            </button>
          </div>
        </div>
      </div>

      {/* ── POSITIONS SECTION ──────────────────────────────────────────────── */}
      {(tab === "all" || tab === "positions") && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <span className="card-title">DHAN LIVE POSITIONS</span>
            <span className="card-badge">
              {(positions ?? []).filter((p: any) => Number(p.net_qty) !== 0).length} open / {(positions ?? []).length} total
            </span>
          </div>
          {posLoading ? (
            <div className="empty-state">Loading positions…</div>
          ) : !positions?.length ? (
            <div className="empty-state">No positions today.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ minWidth: 950 }}>
                <thead>
                  <tr>
                    {["SYMBOL", "EXCH", "PRODUCT", "NET QTY", "STATUS", "BUY", "SELL", "REALIZED", "UNREALIZED", "TOTAL P&L", "ACTION"].map(h => (
                      <th key={h} style={{ textAlign: h === "ACTION" ? "center" : undefined }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p: any) => {
                    const netQty = Number(p.net_qty) || 0;
                    const realized = Number(p.realized) || 0;
                    const unrealized = Number(p.unrealized) || 0;
                    const total = Number(p.total_pnl != null ? p.total_pnl : (realized + unrealized));
                    const isOpen = netQty !== 0;
                    return (
                      <tr key={`${p.symbol}-${p.product_type}`}>
                        <td className="symbol" style={{ fontWeight: 600 }}>{p.symbol}</td>
                        <td style={{ fontSize: 10, color: "var(--muted)" }}>{p.exchange || "—"}</td>
                        <td style={{ fontSize: 11 }}>{p.product_type || "—"}</td>
                        <td
                          style={{
                            fontFamily: "monospace",
                            fontWeight: 700,
                            color: netQty > 0 ? "var(--green)" : netQty < 0 ? "var(--red)" : "var(--muted)",
                          }}
                        >
                          {netQty}
                        </td>
                        <td>
                          <span className={`badge ${isOpen ? "badge-green" : "badge-gray"}`}>
                            {isOpen ? "OPEN" : "CLOSED"}
                          </span>
                        </td>
                        <td style={{ fontSize: 11, fontFamily: "monospace" }}>
                          {p.buy_qty ? `${p.buy_qty} @ ₹${Number(p.buy_avg ?? 0).toFixed(2)}` : "—"}
                        </td>
                        <td style={{ fontSize: 11, fontFamily: "monospace" }}>
                          {p.sell_qty ? `${p.sell_qty} @ ₹${Number(p.sell_avg ?? 0).toFixed(2)}` : "—"}
                        </td>
                        <td className={realized >= 0 ? "pnl-pos" : "pnl-neg"} style={{ fontFamily: "monospace" }}>
                          {`${realized >= 0 ? "+" : ""}₹${realized.toFixed(2)}`}
                        </td>
                        <td className={unrealized >= 0 ? "pnl-pos" : "pnl-neg"} style={{ fontFamily: "monospace" }}>
                          {`${unrealized >= 0 ? "+" : ""}₹${unrealized.toFixed(2)}`}
                        </td>
                        <td className={total >= 0 ? "pnl-pos" : "pnl-neg"} style={{ fontFamily: "monospace", fontWeight: 700 }}>
                          {`${total >= 0 ? "+" : ""}₹${total.toFixed(2)}`}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          {isOpen ? (
                            <button
                              type="button"
                              onClick={() => guardPositionMutation.mutate(p)}
                              disabled={guardPositionMutation.isPending}
                              style={{
                                padding: "3px 8px",
                                fontSize: 10,
                                fontWeight: 700,
                                background: "rgba(0, 230, 118, 0.12)",
                                border: "1px solid rgba(0, 230, 118, 0.4)",
                                color: "var(--green)",
                                borderRadius: 3,
                                cursor: "pointer",
                                whiteSpace: "nowrap",
                              }}
                              title="Import into Algo Window to manage automated profit target exit"
                            >
                              + GUARD ALGO
                            </button>
                          ) : (
                            <span style={{ fontSize: 10, color: "var(--muted)" }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── ORDER BOOK SECTION ──────────────────────────────────────────────── */}
      {(tab === "all" || tab === "orders") && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <span className="card-title">DHAN LIVE ORDER BOOK</span>
            <span className="card-badge">{orderbook?.length ?? 0} orders</span>
          </div>
          {obLoading ? (
            <div className="empty-state">Loading orders…</div>
          ) : !orderbook?.length ? (
            <div className="empty-state">No orders today.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ minWidth: 950 }}>
                <thead>
                  <tr>
                    {["TIME", "SYMBOL", "EXCH", "SIDE", "TYPE", "PRODUCT", "QTY", "PRICE", "AVG ₹", "STATUS", "ORDER ID", "REMARKS"].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {orderbook.map((o: any) => {
                    const statusUpper = String(o.status || "").toUpperCase();
                    const sideUpper = String(o.transaction_type || "").toUpperCase();
                    const isTraded = statusUpper === "TRADED" || statusUpper === "FILLED";
                    const isRejected = statusUpper === "REJECTED" || statusUpper === "CANCELLED";
                    const formattedTime = o.created_at
                      ? (o.created_at.includes("T") ? o.created_at.split("T")[1]?.slice(0, 8) : o.created_at.slice(11, 19))
                      : "—";
                    return (
                      <tr key={o.order_id}>
                        <td style={{ color: "var(--muted)", fontSize: 11, whiteSpace: "nowrap", fontFamily: "monospace" }}>
                          {formattedTime}
                        </td>
                        <td className="symbol" style={{ fontWeight: 600 }}>{o.symbol}</td>
                        <td style={{ fontSize: 10, color: "var(--muted)" }}>{o.exchange || "NSE"}</td>
                        <td>
                          <span className={`badge ${sideUpper === "BUY" ? "badge-green" : "badge-red"}`}>
                            {sideUpper}
                          </span>
                        </td>
                        <td style={{ fontSize: 11 }}>{o.order_type || "—"}</td>
                        <td style={{ fontSize: 11 }}>{o.product_type || "—"}</td>
                        <td style={{ fontFamily: "monospace" }}>
                          {o.filled_qty != null && o.filled_qty !== o.quantity ? `${o.filled_qty}/${o.quantity}` : (o.quantity || "—")}
                        </td>
                        <td style={{ fontFamily: "monospace" }}>
                          {o.price ? `₹${Number(o.price).toLocaleString()}` : "MKT"}
                        </td>
                        <td style={{ fontFamily: "monospace", fontWeight: 600 }}>
                          {o.avg_price ? `₹${Number(o.avg_price).toLocaleString()}` : "—"}
                        </td>
                        <td>
                          <span className={`badge ${isTraded ? "badge-green" : isRejected ? "badge-red" : "badge-yellow"}`}>
                            {statusUpper}
                          </span>
                        </td>
                        <td style={{ fontFamily: "monospace", color: "var(--muted)", fontSize: 11 }}>
                          {o.order_id}
                        </td>
                        <td
                          style={{
                            fontSize: 11,
                            color: isRejected ? "var(--red)" : "var(--muted)",
                            maxWidth: 240,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={o.remarks || ""}
                        >
                          {o.remarks || "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── TRADE HISTORY SECTION ────────────────────────────────────────── */}
      {(tab === "all" || tab === "history") && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="card-title">DHAN ALL TRADE HISTORY & EXECUTIONS</span>
              <span className="card-badge">
                {tradeHistory?.trades?.length ?? 0} trades
              </span>
              {tradeHistory?.summary?.total_pnl != null && (
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: 3,
                    background: tradeHistory.summary.total_pnl >= 0 ? "rgba(0, 230, 118, 0.14)" : "rgba(255, 68, 102, 0.14)",
                    border: `1px solid ${tradeHistory.summary.total_pnl >= 0 ? "var(--green)" : "var(--red)"}`,
                    color: tradeHistory.summary.total_pnl >= 0 ? "var(--green)" : "var(--red)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  REALIZED P&L: {tradeHistory.summary.total_pnl >= 0 ? "+" : ""}₹{Number(tradeHistory.summary.total_pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              )}
            </div>
            {tradeHistory?.summary && (
              <span style={{ fontSize: 11, color: "var(--muted)" }}>
                {tradeHistory.summary.winners ?? 0}W / {tradeHistory.summary.losers ?? 0}L ({tradeHistory.summary.win_rate ?? 0}% Win Rate)
              </span>
            )}
            <button
              type="button"
              onClick={() => {
                if (!tradeHistory?.trades?.length) {
                  toast.error("No trades to export");
                  return;
                }
                exportToCsv("dhan-trade-history.csv", tradeHistory.trades);
                toast.success("Trade history exported as CSV");
              }}
              style={{
                padding: "3px 10px",
                fontSize: 10,
                fontWeight: 700,
                background: "rgba(8,182,222,0.12)",
                border: "1px solid rgba(8,182,222,0.35)",
                color: "var(--ba-cyan)",
                borderRadius: 3,
                cursor: "pointer",
                marginLeft: "auto",
              }}
            >
              EXPORT CSV
            </button>
          </div>
          {thLoading ? (
            <div className="empty-state">Loading trade history…</div>
          ) : !tradeHistory?.trades?.length ? (
            <div className="empty-state">No trade history found.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ minWidth: 950 }}>
                <thead>
                  <tr>
                    {["TIME / DATE", "SYMBOL", "EXCH", "SIDE", "QTY", "ENTRY ₹", "EXIT ₹", "REALIZED P&L", "STATUS", "REASON"].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(tradeHistory.trades ?? []).map((t: any, idx: number) => {
                    const sideUpper = String(t.direction || t.side || "").toUpperCase();
                    const pnl = t.pnl;
                    const isWin = pnl != null && pnl > 0;
                    const isLoss = pnl != null && pnl < 0;
                    const timeStr = t.closed_at || t.created_at || "—";
                    const formattedTime = timeStr.includes("T") ? timeStr.split("T")[0] + " " + timeStr.split("T")[1]?.slice(0, 8) : timeStr;
                    return (
                      <tr key={t.id || idx}>
                        <td style={{ color: "var(--muted)", fontSize: 11, whiteSpace: "nowrap", fontFamily: "monospace" }}>
                          {formattedTime}
                        </td>
                        <td className="symbol" style={{ fontWeight: 600 }}>{t.symbol}</td>
                        <td style={{ fontSize: 10, color: "var(--muted)" }}>{t.exchange || "NSE"}</td>
                        <td>
                          <span className={`badge ${sideUpper === "BUY" ? "badge-green" : "badge-red"}`}>
                            {sideUpper || "—"}
                          </span>
                        </td>
                        <td style={{ fontFamily: "monospace", fontWeight: 600 }}>{t.quantity}</td>
                        <td style={{ fontFamily: "monospace" }}>
                          {t.entry_price ? `₹${Number(t.entry_price).toFixed(2)}` : "—"}
                        </td>
                        <td style={{ fontFamily: "monospace", color: "var(--yellow)" }}>
                          {t.exit_price ? `₹${Number(t.exit_price).toFixed(2)}` : "—"}
                        </td>
                        <td
                          className={isWin ? "pnl-pos" : isLoss ? "pnl-neg" : ""}
                          style={{ fontFamily: "monospace", fontWeight: 700 }}
                        >
                          {pnl != null ? `${isWin ? "+" : ""}₹${Number(pnl).toFixed(2)}` : "—"}
                        </td>
                        <td>
                          <span className={`badge ${t.status === "CLOSED" ? "badge-yellow" : t.status === "OPEN" ? "badge-green" : "badge-gray"}`}>
                            {t.status || "CLOSED"}
                          </span>
                        </td>
                        <td style={{ fontSize: 11, color: "var(--muted)" }}>
                          {t.exit_reason || "EXECUTED"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Layout>
  );
}

// ── Broker Row with inline Edit + Deactivate ──────────────────────────────────
function BrokerRow({ broker: b, qc, onActivate, onRemove, activating }: {
  broker: any; qc: any;
  onActivate: () => void; onRemove: () => void; activating: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [token, setToken]       = useState("");
  const [showToken, setShow]    = useState(false);

  const deactivateMutation = useMutation({
    mutationFn: () => api.patch(`/brokers/${b.id}/deactivate`),
    onSuccess: () => {
      toast.success("Broker deactivated");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
    },
    onError: () => toast.error("Deactivation failed"),
  });

  const renewMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-renew"),
    onSuccess: (res: any) => {
      toast.success(`Token renewed — expires ${res.data?.expires_at ?? "in 24h"}`);
      qc.invalidateQueries({queryKey:["settings-status"]});
      qc.invalidateQueries({queryKey:["dhan-credentials"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
      qc.invalidateQueries({queryKey:["admin-dhan-ip"]});
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Renewal failed — token may be expired"),
  });

  const updateTokenMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-token", {access_token: token}),
    onSuccess: (res: any) => {
      toast.success(res.data?.valid ? "Token updated & verified" : "Token saved");
      qc.invalidateQueries({queryKey:["settings-status"]});
      qc.invalidateQueries({queryKey:["dhan-credentials"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
      qc.invalidateQueries({queryKey:["admin-dhan-ip"]});
      setToken(""); setExpanded(false);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Update failed"),
  });

  return (
    <div style={{borderTop:"1px solid var(--border)"}}>
      {/* Main row */}
      <div style={{
        padding:"10px 14px", display:"flex",
        alignItems:"center", justifyContent:"space-between",
      }}>
        <div style={{display:"flex", alignItems:"center", gap:14}}>
          <div style={{
            width:36, height:36, borderRadius:4,
            background:"rgba(0,255,136,0.1)", border:"1px solid rgba(0,255,136,0.3)",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:13, fontWeight:700, color:"var(--green)",
          }}>{b.broker[0].toUpperCase()}</div>
          <div>
            <div style={{fontWeight:700, fontSize:13}}>{b.broker.toUpperCase()}</div>
            <div style={{fontSize:11, color:"var(--muted)"}}>Client ID: {b.client_id}</div>
          </div>
        </div>

        <div style={{display:"flex", alignItems:"center", gap:8}}>
          <span className={`badge ${b.paper_trading?"badge-yellow":"badge-green"}`}>
            {b.paper_trading ? "PAPER" : "LIVE"}
          </span>
          <span className={`badge ${b.is_active?"badge-green":"badge-gray"}`}>
            {b.is_active ? "ACTIVE" : "INACTIVE"}
          </span>

          {/* Activate / Deactivate */}
          {!b.is_active ? (
            <button className="connect-btn" style={{padding:"5px 12px", fontSize:10}}
              onClick={onActivate} disabled={activating}>
              {activating ? "..." : "ACTIVATE"}
            </button>
          ) : (
            <button className="exit-btn"
              style={{padding:"5px 12px", fontSize:10,
                color:"var(--yellow)", borderColor:"rgba(255,183,3,0.3)"}}
              onClick={() => deactivateMutation.mutate()}
              disabled={deactivateMutation.isPending}>
              {deactivateMutation.isPending ? "..." : "DEACTIVATE"}
            </button>
          )}

          {/* Edit token */}
          {!b.paper_trading && (
            <button
              onClick={() => setExpanded(v => !v)}
              style={{
                padding:"5px 12px", fontSize:10, cursor:"pointer",
                fontFamily:"var(--font)",
                background: expanded ? "rgba(0,255,136,0.1)" : "transparent",
                border: `1px solid ${expanded ? "rgba(0,255,136,0.4)" : "var(--border)"}`,
                color: expanded ? "var(--green)" : "var(--muted)",
              }}>
              {expanded ? "CLOSE" : "EDIT TOKEN"}
            </button>
          )}

          <button className="exit-btn" onClick={onRemove}>REMOVE</button>
        </div>
      </div>

      {/* Expanded token edit panel */}
      {expanded && !b.paper_trading && (
        <div style={{
          margin:"0 20px 16px",
          padding:"16px",
          background:"rgba(0,0,0,0.2)",
          border:"1px solid var(--border)",
        }}>
          <div style={{fontSize:11, color:"var(--muted)", marginBottom:12}}>
            Get new token from{" "}
            <a href="https://web.dhan.co" target="_blank" rel="noreferrer"
              style={{color:"var(--green)"}}>web.dhan.co</a>
            {" → My Profile → Access DhanHQ APIs → Generate Token"}
          </div>

          {/* Auto renew */}
          <div style={{marginBottom:12}}>
            <span style={{fontSize:11, color:"var(--muted)", marginRight:10}}>
              Token still active?
            </span>
            <button
              className={`connect-btn${renewMutation.isPending?" loading":""}`}
              onClick={() => renewMutation.mutate()}
              disabled={renewMutation.isPending}
              style={{fontSize:10, padding:"4px 12px"}}>
              {renewMutation.isPending ? "RENEWING..." : "⟳ AUTO RENEW (extends 24h)"}
            </button>
          </div>

          {/* Manual token paste */}
          <div style={{display:"flex", gap:8, alignItems:"center"}}>
            <div style={{position:"relative", flex:1}}>
              <input className="field-input"
                type={showToken ? "text" : "password"}
                value={token}
                onChange={e => setToken(e.target.value)}
                placeholder="Paste new token (eyJ...) — use when expired"
                style={{paddingRight:60, width:"100%"}} />
              <button onClick={() => setShow(v => !v)} style={{
                position:"absolute", right:10, top:"50%",
                transform:"translateY(-50%)", background:"transparent",
                border:"none", color:"var(--muted)", cursor:"pointer", fontSize:10,
              }}>{showToken ? "HIDE" : "SHOW"}</button>
            </div>
            <button
              className={`connect-btn${updateTokenMutation.isPending?" loading":""}`}
              onClick={() => updateTokenMutation.mutate()}
              disabled={!token.trim() || updateTokenMutation.isPending}
              style={{whiteSpace:"nowrap", fontSize:10}}>
              {updateTokenMutation.isPending ? "..." : "UPDATE →"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
