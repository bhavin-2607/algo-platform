import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";

interface CompareRow {
  engine_class: string;
  version: string;
  has_run: boolean;
  passed: boolean | null;
  total_pnl: number | null;
  max_drawdown: number | null;
  trade_count: number | null;
  created_at: string | null;
}

export default function GuidePage() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [querySymbol, setQuerySymbol] = useState("RELIANCE");
  const { data, isFetching, error } = useQuery({
    queryKey: ["backtest-compare", querySymbol],
    queryFn: async () => {
      const res = await api.get("/backtest/compare", { params: { symbol: querySymbol } });
      return res.data as { symbol: string; engines: CompareRow[] };
    },
  });

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">GUIDE</h1>
          <p className="page-sub">Compare stored paper backtests, then the three checks before live capital</p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><span className="card-title">PAPER COMPARISON</span></div>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Latest saved run for each engine on one symbol. This does not call Dhan. Run a backtest first, then come back here.
        </p>
        <form
          onSubmit={(e) => { e.preventDefault(); setQuerySymbol(symbol.trim().toUpperCase() || "RELIANCE"); }}
          style={{ display: "flex", gap: 8, margin: "12px 0" }}
        >
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            aria-label="Symbol"
            style={{ background: "#0d1117", color: "#e8f5e9", border: "1px solid rgba(0,255,136,0.3)", padding: "8px 10px", fontFamily: "inherit" }}
          />
          <button type="submit" className="tab-btn active">COMPARE</button>
        </form>
        {isFetching && <p className="page-sub">Loading stored runs…</p>}
        {error && <p className="page-sub">Could not load comparison.</p>}
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#8b9bb4" }}>
              <th>Engine</th><th>Version</th><th>Trades</th><th>Net PnL</th><th>Max DD</th><th>Result</th>
            </tr>
          </thead>
          <tbody>
            {(data?.engines || []).map((row) => (
              <tr key={`${row.engine_class}-${row.version}`} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                <td>{row.engine_class}</td>
                <td>{row.version}</td>
                <td>{row.has_run ? row.trade_count : "—"}</td>
                <td>{row.has_run ? row.total_pnl : "—"}</td>
                <td>{row.has_run ? row.max_drawdown : "—"}</td>
                <td>{row.has_run ? (row.passed ? "PASS" : "FAIL") : "NO RUN"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><span className="card-title">ADD A STRATEGY</span></div>
        <ol>
          <li>Drop one Python file in the repo <code>strategy/</code> folder. It needs one <code>BaseStrategy</code> subclass, an <code>engine_id</code>, and a <code>version</code>.</li>
          <li>Reload plugins from Admin, then create the catalogue row. Paper assign is allowed immediately.</li>
          <li>Live start stays blocked until an admin enables that version. A newer code version than the one you assigned also blocks live start.</li>
        </ol>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><span className="card-title">WRITE A FORMULA</span></div>
        <ol>
          <li>Use the allow-list: <code>ma</code>, <code>ema</code>, <code>rsi</code>, <code>vwap</code>, <code>atr</code>, <code>bb_upper</code>, <code>bb_lower</code>, <code>supertrend</code>, <code>abs</code>, <code>min</code>, <code>max</code>, <code>round</code>.</li>
          <li>On the formula form, Preview entry on Dhan history before you save. A bad expression is rejected and the message stays under that field.</li>
          <li>A formula that calls Python, imports modules, or exceeds the length and node limits will not save.</li>
        </ol>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">GO-LIVE CHECKS</span></div>
        <ol>
          <li>Each machine has its own empty database, its own <code>.env</code>, and its public IPv4 whitelisted at Dhan. Leave <code>LIVE_TRADING_ENABLED</code> off until the proof runs below are done on that machine.</li>
          <li>Run a paper session on bar closes for each engine and formula you will use. Confirm a real fill at Dhan, use the kill switch once and see it flatten, then restart with a position still open and confirm the position and the risk counters.</li>
          <li>The latest backtest for that engine version and symbol must not be a loss. A missing backtest does not block. The server edition alerts on a stale feed, the kill switch, and live order rejects at Prometheus port 9090.</li>
        </ol>
      </div>
    </Layout>
  );
}
