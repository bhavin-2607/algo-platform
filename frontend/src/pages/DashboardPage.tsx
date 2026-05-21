import { useQuery } from "@tanstack/react-query";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import Layout from "@/components/common/Layout";
import { tradesApi, brokerApi } from "@/utils/api";
import { useAuthStore } from "@/store/auth";

const MOCK_PNL = [
  { day: "Mon", pnl: 1200 }, { day: "Tue", pnl: 3400 }, { day: "Wed", pnl: 2100 },
  { day: "Thu", pnl: 5600 }, { day: "Fri", pnl: 4200 }, { day: "Sat", pnl: 7800 },
  { day: "Sun", pnl: 6500 },
];

export default function DashboardPage() {
  const { user } = useAuthStore();

  const { data: summary } = useQuery({
    queryKey: ["trade-summary"],
    queryFn: () => tradesApi.summary().then(r => r.data),
    refetchInterval: 30_000,
  });

  const { data: trades } = useQuery({
    queryKey: ["recent-trades"],
    queryFn: () => tradesApi.list({ limit: 5 }).then(r => r.data),
  });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => brokerApi.list().then(r => r.data),
  });

  const openPositions = trades?.filter((t: any) => t.status === "OPEN") ?? [];

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">DASHBOARD</h1>
          <p className="page-sub">
            Welcome back, <span style={{ color: "var(--green)" }}>{user?.username}</span>
          </p>
        </div>
        <div className="market-status">
          <div className="market-dot" />
          <span>MARKET OPEN</span>
        </div>
      </div>

      {/* Stat cards — real data with fallback */}
      <div className="stats-grid">
        <StatCard
          label="TODAY'S P&L"
          value={`₹${(summary?.today_pnl ?? 0).toLocaleString()}`}
          delta={summary?.today_pnl >= 0 ? "Profitable day" : "Loss day"}
          positive={summary?.today_pnl >= 0}
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
          value={brokers?.length ? brokers[0].broker.toUpperCase() : "NONE"}
          delta={brokers?.length ? (brokers[0].paper_trading ? "Paper mode" : "Live mode") : "Not connected"}
          neutral
        />
      </div>

      {/* P&L Chart */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <span className="card-title">WEEKLY P&L</span>
          <span className="card-badge">PAPER MODE</span>
        </div>
        <div style={{ padding: "8px 0 0" }}>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={MOCK_PNL} margin={{ left: 10, right: 20, top: 10, bottom: 0 }}>
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

      {/* Recent trades from real API */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">RECENT TRADES</span>
          <span className="card-badge">{summary?.total_trades ?? 0} total</span>
        </div>

        {(!trades || trades.length === 0) ? (
          <div className="empty-state">
            No trades yet — start a strategy to see trades here.
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
                        {t.created_at ? new Date(t.created_at).toLocaleTimeString() : "—"}
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
