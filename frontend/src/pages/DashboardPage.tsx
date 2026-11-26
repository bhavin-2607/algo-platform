import { useQuery } from "@tanstack/react-query";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import Layout from "@/components/common/Layout";
import { tradesApi, brokerApi, api } from "@/utils/api";
import { useAuthStore } from "@/store/auth";



export default function DashboardPage() {
  const { user } = useAuthStore();
  const { data: dhanHistory, isLoading: historyLoading, isError: historyError } = useQuery({
    queryKey: ["dhan-trade-history"],
    queryFn: () => api.get("/terminal/trade-history").then(r => r.data),
    refetchInterval: 60_000,
    retry: false,
  });
  const dhanConnected = dhanHistory?.connected === true;
  const showPaper = !historyLoading && !historyError && dhanHistory?.connected === false;

  const { data: weeklyPnlPaper } = useQuery({
    queryKey: ["weekly-pnl"],
    queryFn: () => api.get("/trades/weekly-pnl").then(r => r.data),
    refetchInterval: 30_000,
    enabled: showPaper,
  });

  const { data: summaryPaper } = useQuery({
    queryKey: ["trade-summary"],
    queryFn: () => tradesApi.summary().then(r => r.data),
    refetchInterval: 30_000,
    enabled: showPaper,
  });

  const { data: paperTrades } = useQuery({
    queryKey: ["recent-trades"],
    queryFn: () => api.get("/trades?limit=20&is_paper=true").then(r => r.data),
    enabled: showPaper,
  });

  const summary = dhanConnected ? dhanHistory.summary : summaryPaper;
  const weeklyPnl = dhanConnected ? dhanHistory.weekly : weeklyPnlPaper;
  const trades = dhanConnected ? dhanHistory.trades : paperTrades;

  const { data: brokerOrders } = useQuery({
    queryKey: ["orderbook"],
    queryFn: () => api.get("/terminal/orderbook").then(r => r.data),
    refetchInterval: 10_000,
  });

  const { data: brokerPositions } = useQuery({
    queryKey: ["dhan-positions"],
    queryFn: () => api.get("/terminal/positions").then(r => r.data),
    refetchInterval: 10_000,
  });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => brokerApi.list().then(r => r.data),
  });

  const openPositions = (brokerPositions ?? []).filter((p: any) => Number(p.net_qty) !== 0);

  // Compute live Today P&L from broker positions (realized + unrealized) with fallback to trade summary
  const positionsRealized = (brokerPositions ?? []).reduce((acc: number, p: any) => acc + (Number(p.realized) || 0), 0);
  const positionsUnrealized = (brokerPositions ?? []).reduce((acc: number, p: any) => acc + (Number(p.unrealized) || 0), 0);
  const livePositionsPnl = positionsRealized + positionsUnrealized;
  const todayPnl = (brokerPositions && brokerPositions.length > 0)
    ? livePositionsPnl
    : (summary?.today_pnl ?? 0);

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">DASHBOARD</h1>
          <p className="page-sub">
            Welcome back, <span style={{ color: "var(--green)" }}>{user?.username}</span>
          </p>
        </div>
      </div>

      {/* Stat cards — real data with fallback */}
      <div className="stats-grid">
        <StatCard
          label="TODAY'S P&L"
          value={`${todayPnl >= 0 ? "+" : ""}₹${Number(todayPnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          delta={todayPnl > 0 ? "Profitable day" : todayPnl < 0 ? "Loss day" : "Break-even"}
          positive={todayPnl > 0}
          neutral={todayPnl === 0}
        />
        <StatCard
          label="TOTAL P&L"
          value={`₹${(summary?.total_pnl ?? 0).toLocaleString()}`}
          delta={`${summary?.closed_trades ?? 0} closed trades`}
          positive={(summary?.total_pnl ?? 0) >= 0}
        />
        <StatCard
          label="WIN RATE"
          value={`${summary?.win_rate ?? 0}%`}
          delta={`${summary?.winners ?? 0}W / ${summary?.losers ?? 0}L`}
          positive={(summary?.win_rate ?? 0) >= 50}
        />
        <StatCard
          label="BROKER"
          value="DHAN"
          delta={dhanConnected ? "Live Connected" : "Paper Trading Active"}
          positive={dhanConnected}
          neutral={!dhanConnected}
        />
      </div>

      {/* P&L Chart */}
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="card-header">
          <span className="card-title">WEEKLY P&L</span>
          <span className="card-badge">{dhanConnected ? "DHAN LIVE" : "PAPER"}</span>
        </div>
        <div style={{ padding: "8px 0 0" }}>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={weeklyPnl ?? []} margin={{ left: 10, right: 20, top: 10, bottom: 0 }}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00ff88" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="day" tick={{ fill: "#4a5568", fontSize: 11, fontFamily: "inherit" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#4a5568", fontSize: 11, fontFamily: "inherit" }} axisLine={false} tickLine={false}
                tickFormatter={(v) => `₹${(v/1000).toFixed(0)}k`} />
              <Tooltip
                contentStyle={{ background: "#0d1117", border: "1px solid #00ff88", borderRadius: 0, fontFamily: "inherit", fontSize: 12 }}
                labelStyle={{ color: "#00ff88" }} itemStyle={{ color: "#e8f5e9" }}
                formatter={(v: any) => [`₹${Number(v).toLocaleString()}`, "P&L"]}
              />
              <Area type="monotone" dataKey="pnl" stroke="#00ff88" strokeWidth={2} fill="url(#pnlGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Live Orderbook with Full Execution Details */}
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="card-header">
          <span className="card-title">DHAN LIVE ORDERBOOK</span>
          <span className="card-badge">{brokerOrders?.length ?? 0} orders</span>
        </div>
        {!brokerOrders?.length ? (
          <div className="empty-state">No Dhan orders today.</div>
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
                {(brokerOrders ?? []).map((o: any) => {
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

      {/* Live Positions with Full P&L Breakdown */}
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="card-header">
          <span className="card-title">DHAN LIVE POSITIONS</span>
          <span className="card-badge">{openPositions.length} open / {(brokerPositions ?? []).length} total</span>
        </div>
        {!brokerPositions?.length ? (
          <div className="empty-state">No Dhan positions today.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ minWidth: 900 }}>
              <thead>
                <tr>
                  {["SYMBOL", "EXCH", "PRODUCT", "NET QTY", "STATUS", "BUY", "SELL", "REALIZED", "UNREALIZED", "TOTAL P&L"].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(brokerPositions ?? []).map((p: any) => {
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
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent trades from real API */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">{dhanConnected ? "DHAN TRADES" : "PAPER TRADES"}</span>
          <span className="card-badge">{summary?.total_trades ?? 0} total</span>
        </div>

        {(!trades || trades.length === 0) ? (
          <div className="empty-state">
            {historyError
              ? "Dhan trade history did not load."
              : dhanConnected
              ? "No Dhan trades in the last 90 days."
              : historyLoading
              ? "Loading Dhan trades..."
              : "Dhan is not connected. Paper trades show here until it is."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ minWidth: 900 }}>
              <thead>
                <tr>
                  {["SYMBOL","SIDE","QTY","ENTRY ₹","EXIT ₹","STOP LOSS","TARGET","P&L","P&L %","EXIT REASON","STATUS","MODE","TIME"].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((t: any) => {
                  const pnl    = t.pnl;
                  const pnlPct = t.pnl_pct;
                  return (
                    <tr key={t.id}>
                      <td className="symbol">{t.symbol}<br/>
                        <span style={{ fontSize: 9, color: "var(--muted)", letterSpacing: 1 }}>{t.exchange}</span>
                      </td>
                      <td>
                        <span className={`badge ${t.direction === "BUY" ? "badge-green" : "badge-red"}`}>
                          {t.direction}
                        </span>
                      </td>
                      <td>{t.quantity}</td>
                      <td style={{ fontWeight: 600 }}>
                        {t.entry_price ? `₹${Number(t.entry_price).toLocaleString()}` : "—"}
                      </td>
                      <td style={{ color: "var(--muted)" }}>
                        {t.exit_price ? `₹${Number(t.exit_price).toLocaleString()}` : "—"}
                      </td>
                      <td style={{ color: "var(--red)", fontSize: 11 }}>
                        {t.stop_loss ? `₹${Number(t.stop_loss).toLocaleString()}` : "—"}
                      </td>
                      <td style={{ color: "var(--green)", fontSize: 11 }}>
                        {t.target_price ? `₹${Number(t.target_price).toLocaleString()}` : "—"}
                      </td>
                      <td className={pnl == null ? "" : pnl >= 0 ? "pnl-pos" : "pnl-neg"}>
                        {pnl == null ? "—" : `${pnl >= 0 ? "+" : ""}₹${Number(pnl).toLocaleString()}`}
                      </td>
                      <td className={pnlPct == null ? "" : pnlPct >= 0 ? "pnl-pos" : "pnl-neg"} style={{ fontSize: 11 }}>
                        {pnlPct == null ? "—" : `${pnlPct >= 0 ? "+" : ""}${Number(pnlPct).toFixed(2)}%`}
                      </td>
                      <td>
                        {t.exit_reason ? (
                          <span className={`badge ${
                            t.exit_reason === "TARGET_HIT" ? "badge-green" :
                            t.exit_reason === "SL_HIT"     ? "badge-red"   : "badge-gray"
                          }`} style={{ fontSize: 9 }}>
                            {t.exit_reason.replace("_", " ")}
                          </span>
                        ) : "—"}
                      </td>
                      <td>
                        <span className={`badge ${
                          t.status === "CLOSED"  ? "badge-gray"   :
                          t.status === "OPEN"    ? "badge-green"  : "badge-yellow"
                        }`}>{t.status}</span>
                      </td>
                      <td>
                        <span className={`badge ${t.is_paper ? "badge-yellow" : "badge-red"}`}>
                          {t.is_paper ? "PAPER" : "LIVE"}
                        </span>
                      </td>
                      <td style={{ color: "var(--muted)", fontSize: 10, whiteSpace: "nowrap" }}>
                        {(t.closed_at || t.created_at)
                          ? new Date(t.closed_at || t.created_at).toLocaleString()
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
}

function StatCard({ label, value, delta, positive, neutral }: any) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className={`stat-delta ${positive ? "pos" : neutral ? "neu" : "neg"}`}>{delta}</div>
    </div>
  );
}
