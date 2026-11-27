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

  const { data: funds } = useQuery({
    queryKey: ["dhan-funds"],
    queryFn: () => api.get("/market/funds").then(r => r.data),
    refetchInterval: 30_000,
  });

  const { data: holdings } = useQuery({
    queryKey: ["dhan-holdings"],
    queryFn: () => api.get("/terminal/holdings").then(r => r.data as any[]),
    refetchInterval: 30_000,
  });

  const { data: tokenStatus } = useQuery({
    queryKey: ["dhan-auth-token-status"],
    queryFn: () => api.get("/dhan-auth/token-status").then(r => r.data),
    refetchInterval: 60_000,
  });

  const { data: dhanProfile } = useQuery({
    queryKey: ["dhan-profile"],
    queryFn: () => api.get("/terminal/dhan-profile").then(r => r.data),
    refetchInterval: 60_000,
  });

  const holdingsList = holdings || [];
  const totalInvestment = holdingsList.reduce(
    (acc: number, h: any) => acc + (Number(h.totalQty || h.quantity || 0) * Number(h.avgCostPrice || h.averagePrice || 0)),
    0
  );
  const totalHoldingsVal = holdingsList.reduce(
    (acc: number, h: any) =>
      acc +
      (Number(h.totalQty || h.quantity || 0) *
        Number(h.lastTradedPrice || h.ltp || h.closePrice || h.avgCostPrice || 0)),
    0
  );
  const totalHoldingsPnl = totalHoldingsVal - totalInvestment;
  const totalHoldingsPnlPct = totalInvestment > 0 ? (totalHoldingsPnl / totalInvestment) * 100 : 0;

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
      {/* ── PROFILE & BROKER CONNECTIVITY CARD ───────────────────────────── */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header" style={{ padding: "8px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className="card-title" style={{ fontSize: 11, letterSpacing: 1.2 }}>ACCOUNT PROFILE & BROKER CONNECTIVITY</span>
            <span className={`badge ${dhanConnected ? "badge-green" : "badge-yellow"}`} style={{ fontSize: 9 }}>
              {dhanConnected ? "DHAN LIVE BROKER" : "PAPER TRADING"}
            </span>
            {tokenStatus?.valid ? (
              <span className="badge badge-green" style={{ fontSize: 9 }}>
                TOKEN VALID ({typeof tokenStatus.hours_remaining === "number" ? tokenStatus.hours_remaining.toFixed(1) : 16}H LEFT)
              </span>
            ) : (
              <span className="badge badge-yellow" style={{ fontSize: 9 }}>
                TOKEN AUTH CYCLE
              </span>
            )}
            {dhanProfile?.dataPlan && (
              <span className={`badge ${dhanProfile.dataPlan.toLowerCase() === "active" ? "badge-green" : "badge-gray"}`} style={{ fontSize: 9 }}>
                DATA FEED: {dhanProfile.dataPlan.toUpperCase()}
              </span>
            )}
            {dhanProfile?.ddpi && (
              <span className={`badge ${dhanProfile.ddpi.toLowerCase() === "active" ? "badge-green" : "badge-gray"}`} style={{ fontSize: 9 }}>
                DDPI: {dhanProfile.ddpi.toUpperCase()}
              </span>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "monospace" }}>
            DHAN CLIENT ID: <span style={{ color: "var(--green)", fontWeight: 700 }}>{dhanProfile?.dhanClientId || tokenStatus?.client_id || user?.username}</span>
          </div>
        </div>

        {/* Funds & Margin Row */}
        <div style={{ padding: "10px 14px 6px 14px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>AVAILABLE CASH MARGIN</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--green)", marginTop: 2, fontFamily: "monospace" }}>
              ₹{Number(funds?.availabelBalance || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>UTILIZED MARGIN</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--yellow)", marginTop: 2, fontFamily: "monospace" }}>
              ₹{Number(funds?.utilizedAmount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>SOD LIMIT / COLLATERAL</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", marginTop: 2, fontFamily: "monospace" }}>
              ₹{Number(funds?.sodLimit || funds?.collateralAmount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>PLATFORM USER</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginTop: 2 }}>
              {user?.username} <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: 400 }}>({user?.role})</span>
            </div>
          </div>
        </div>

        {/* Dhan Account & Trading Telemetry Row */}
        <div style={{ padding: "0 14px 10px 14px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>ACTIVE SEGMENTS</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
              {dhanProfile?.segments && dhanProfile.segments.length > 0 ? (
                dhanProfile.segments.map((s: string, idx: number) => (
                  <span key={idx} className="badge badge-gray" style={{ fontSize: 9, padding: "2px 5px", background: "rgba(0,230,118,0.08)", color: "var(--green)", borderColor: "rgba(0,230,118,0.25)" }}>
                    {s}
                  </span>
                ))
              ) : (
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  {dhanProfile?.activeSegment || "Equity, F&O, Currency, Commodity"}
                </span>
              )}
            </div>
          </div>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>DATA PLAN & VALIDITY</div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginTop: 3 }}>
              {dhanProfile?.dataPlan ? dhanProfile.dataPlan : "Active"}
              {dhanProfile?.dataValidity && (
                <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "monospace", marginTop: 2 }}>
                  Valid: {dhanProfile.dataValidity.slice(0, 10)}
                </div>
              )}
            </div>
          </div>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>DDPI & MTF PRIVILEGES</div>
            <div style={{ display: "flex", gap: 6, marginTop: 4, alignItems: "center" }}>
              <span className={`badge ${dhanProfile?.ddpi?.toLowerCase() === "active" ? "badge-green" : "badge-gray"}`} style={{ fontSize: 9 }}>
                DDPI: {dhanProfile?.ddpi || "Deactive"}
              </span>
              <span className={`badge ${dhanProfile?.mtf?.toLowerCase() === "active" ? "badge-green" : "badge-gray"}`} style={{ fontSize: 9 }}>
                MTF: {dhanProfile?.mtf || "Deactive"}
              </span>
            </div>
          </div>
          <div style={{ background: "var(--surface2)", padding: "8px 10px", borderRadius: 4, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>SESSION TOKEN EXPIRATION</div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", marginTop: 3, fontFamily: "monospace" }}>
              {dhanProfile?.tokenValidity || tokenStatus?.expires_at_ist || tokenStatus?.expires_at || "Daily 24H Cycle"}
            </div>
          </div>
        </div>
      </div>

      {/* ── PORTFOLIO & HOLDINGS CARD ────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header" style={{ padding: "8px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className="card-title" style={{ fontSize: 11, letterSpacing: 1.2 }}>PORTFOLIO HOLDINGS & EQUITY SUMMARY</span>
            <span className="badge badge-gray" style={{ fontSize: 9 }}>
              {holdingsList.length} STOCKS
            </span>
            {holdingsList.length > 0 && (
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "2px 8px",
                  borderRadius: 3,
                  background: totalHoldingsPnl >= 0 ? "rgba(0, 230, 118, 0.14)" : "rgba(255, 68, 102, 0.14)",
                  border: `1px solid ${totalHoldingsPnl >= 0 ? "var(--green)" : "var(--red)"}`,
                  color: totalHoldingsPnl >= 0 ? "var(--green)" : "var(--red)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                UNREALIZED P&L: {totalHoldingsPnl >= 0 ? "+" : ""}₹{totalHoldingsPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ({totalHoldingsPnlPct >= 0 ? "+" : ""}{totalHoldingsPnlPct.toFixed(2)}%)
              </span>
            )}
          </div>
          {holdingsList.length > 0 && (
            <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "monospace" }}>
              CURRENT VALUE: <span style={{ color: "var(--text)", fontWeight: 700 }}>₹{totalHoldingsVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
          )}
        </div>
        {holdingsList.length === 0 ? (
          <div style={{ padding: "20px 14px", color: "var(--muted)", fontSize: 12, textAlign: "center" }}>
            No active long-term equity holdings in Dhan portfolio.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ minWidth: 800 }}>
              <thead>
                <tr>
                  {["SYMBOL", "EXCHANGE", "QUANTITY", "AVG COST ₹", "LTP ₹", "CURRENT VALUE ₹", "UNREALIZED P&L"].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {holdingsList.map((h: any, idx: number) => {
                  const qty = Number(h.totalQty || h.quantity || 0);
                  const avgCost = Number(h.avgCostPrice || h.averagePrice || 0);
                  const ltp = Number(h.lastTradedPrice || h.ltp || h.closePrice || avgCost);
                  const curVal = qty * ltp;
                  const invested = qty * avgCost;
                  const pnl = curVal - invested;
                  const isPos = pnl >= 0;
                  return (
                    <tr key={h.tradingSymbol || h.securityId || idx}>
                      <td className="symbol" style={{ fontWeight: 600 }}>{h.tradingSymbol || h.symbol || h.securityId}</td>
                      <td style={{ fontSize: 10, color: "var(--muted)" }}>{h.exchange || "NSE"}</td>
                      <td style={{ fontFamily: "monospace", fontWeight: 700 }}>{qty}</td>
                      <td style={{ fontFamily: "monospace" }}>₹{avgCost.toFixed(2)}</td>
                      <td style={{ fontFamily: "monospace", fontWeight: 600 }}>₹{ltp.toFixed(2)}</td>
                      <td style={{ fontFamily: "monospace" }}>₹{curVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className={isPos ? "pnl-pos" : "pnl-neg"} style={{ fontFamily: "monospace", fontWeight: 700 }}>
                        {isPos ? "+" : ""}₹{pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
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
