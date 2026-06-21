/**
 * Trade Terminal
 * ==============
 * Unified terminal merging Live Market data + Trade execution
 * Modelled exactly after the Excel Trade Terminal layout:
 *   Row 1: Account summary (Cash, Margin, Overall PnL, Order Type, Trade Mode)
 *   Row 3+: Per-symbol rows with OHLC, VWAP, Best Buy/Sell, LTP, signals, entry/exit, T/SL, PnL
 */
import { useState, useEffect, useRef, useMemo, useCallback } from "react";
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
  // Live market data (from Dhan)
  ltp: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  vwap: number | null;
  volume: number | null;
  oi: number | null;
  bp1: number | null;  // best buy price
  sp1: number | null;  // best sell price
  change_pct: number | null;
  // Trade data
  signal: string;
  entry_price: number | null;
  entry_order_id: string | null;
  entry_remarks: string | null;
  current_sl: number | null;
  current_target: number | null;
  trailing_sl_enabled: boolean;
  latest_sl: number | null;
  pnl: number | null;
  // Admin only
  entry_formula?: string;
  exit_formula?: string;
}


// ── Excel Formula Evaluator (frontend) ───────────────────────────────────────
// Supports: named fields, cell refs, cross-column refs (SIGNAL/ENTRY),
//           ^ power, % percent, <> not-equal, IF/AND/OR/ROUND/SQRT etc.
function evalExcelFormula(
  formula: string,
  tick: Record<string,any>,
  colValues?: Record<string,any>
): string | number | null {
  if (!formula) return null;
  let expr = formula.startsWith("=") ? formula.slice(1) : formula;

  // 1. Percentage literals: 0.5% → (0.5/100)
  expr = expr.replace(/(\d+\.?\d*)\s*%/g, "($1/100)");

  // 2. Cross-column references (SIGNAL, ENTRY, TREND etc.)
  if (colValues) {
    Object.entries(colValues).forEach(([colName, colVal]) => {
      if (colVal != null) {
        const re = new RegExp("\\b" + colName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "g");
        const rep = typeof colVal === "string" ? "'" + colVal + "'" : String(colVal);
        expr = expr.replace(re, rep);
      }
    });
  }

  // 3. Named field references (must come before cell refs)
  const namedFields: Record<string, string> = {
    open: "open", high: "high", low: "low", close: "close",
    vwap: "vwap", atp: "atp",  ltp: "ltp", volume: "volume",
    oi: "oi", change_pct: "change_pct", bp1: "bp1", sp1: "sp1",
  };
  Object.entries(namedFields).forEach(([name, field]) => {
    const re = new RegExp("\\b" + name + "\\b", "gi");
    expr = expr.replace(re, String(parseFloat(tick[field] ?? 0) || 0));
  });

  // 4. Cell references: C4 → high value
  const cellMap: Record<string, string> = {
    B: "open", C: "high", D: "low",  E: "close",
    F: "vwap", G: "bp1",  H: "sp1",  I: "volume",
    J: "oi",   K: "ltp",  L: "change_pct", M: "atp",
  };
  expr = expr.replace(/\b([A-Z]{1,2})\d+\b/g, (_: string, col: string) => {
    const field = cellMap[col.toUpperCase()];
    return String(parseFloat(tick[field] ?? 0) || 0);
  });

  // 5. Operators
  expr = expr.replace(/<>/g, "!==");
  expr = expr.replace(/\^/g, "**");
  // 0.5% → 0.005
  expr = expr.replace(/(\d+\.?\d*)\s*%/g, (_:string, n:string) => String(parseFloat(n) / 100));
  // Excel = is equality → JS === (but not <=, >=, !=, ==)
  expr = expr.replace(/(?<![<>!=])=(?!=)/g, "===");

  // 6. Excel functions → JS helpers
  expr = expr.replace(/\bIF\s*\(/gi,      "_IF(");
  expr = expr.replace(/\bAND\s*\(/gi,     "_AND(");
  expr = expr.replace(/\bOR\s*\(/gi,      "_OR(");
  expr = expr.replace(/\bAVERAGE\s*\(/gi, "_AVG(");
  expr = expr.replace(/\bROUND\s*\(/gi,   "_ROUND(");
  expr = expr.replace(/\bIFERROR\s*\(/gi, "_IFERROR(");
  expr = expr.replace(/\bSQRT\s*\(/gi,    "Math.sqrt(");
  expr = expr.replace(/\bPOWER\s*\(/gi,   "_POW(");
  expr = expr.replace(/\bABS\s*\(/gi,     "Math.abs(");
  expr = expr.replace(/\bMAX\s*\(/gi,     "Math.max(");
  expr = expr.replace(/\bMIN\s*\(/gi,     "Math.min(");
  expr = expr.replace(/\bINT\s*\(/gi,     "Math.trunc(");

  // 7. String literals: "BUY" → 'BUY'
  expr = expr.replace(/"/g, "'");

  try {
    const _IF     = (c: any, t: any, f: any) => c ? t : f;
    const _AND    = (...a: any[]) => a.every(Boolean);
    const _OR     = (...a: any[]) => a.some(Boolean);
    const _AVG    = (...a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
    const _ROUND  = (v: number, d = 0) => { const f = 10 ** d; return Math.round(v * f) / f; };
    const _POW    = (b: number, e: number) => Math.pow(b, e);
    const _IFERROR = (v: any, fallback: any = "") => (v == null ? fallback : v);
    // eslint-disable-next-line no-new-func
    const result = new Function(
      "_IF", "_AND", "_OR", "_AVG", "_ROUND", "_POW", "_IFERROR", "Math",
      `"use strict"; return (${expr});`
    )(_IF, _AND, _OR, _AVG, _ROUND, _POW, _IFERROR, Math);
    if (typeof result === "number") return isFinite(result) ? Math.round(result * 100) / 100 : null;
    if (typeof result === "string") return result.trim() === "" ? null : result.trim();
    return result;
  } catch {
    return null;
  }
}

// Get color for a formula column value based on color_rules
function getColColor(value: any, colorRules: string | null): string {
  if (!colorRules || value == null) return "var(--text)";
  try {
    const rules = JSON.parse(colorRules);
    const key   = String(value);
    const color = rules[key] ?? rules[key.toLowerCase()];
    if (color === "green")  return "var(--green)";
    if (color === "red")    return "var(--red)";
    if (color === "yellow") return "var(--yellow)";
    if (color === "muted")  return "var(--muted)";
    // positive/negative rules
    if (typeof value === "number") {
      if (value > 0 && rules["positive"]) {
        const c = rules["positive"];
        if (c === "green") return "var(--green)";
        if (c === "red")   return "var(--red)";
      }
      if (value < 0 && rules["negative"]) {
        const c = rules["negative"];
        if (c === "green") return "var(--green)";
        if (c === "red")   return "var(--red)";
      }
    }
  } catch {}
  return "var(--text)";
}

const SECURITY_IDS: Record<string, {security_id:string, segment:string}> = {
  "NIFTY50":    {security_id:"13",    segment:"IDX_I"},
  "BANKNIFTY":  {security_id:"25",    segment:"IDX_I"},
  "RELIANCE":   {security_id:"2885",  segment:"NSE_EQ"},
  "TCS":        {security_id:"11536", segment:"NSE_EQ"},
  "INFY":       {security_id:"1594",  segment:"NSE_EQ"},
  "HDFCBANK":   {security_id:"1333",  segment:"NSE_EQ"},
  "ICICIBANK":  {security_id:"4963",  segment:"NSE_EQ"},
  "SBIN":       {security_id:"3045",  segment:"NSE_EQ"},
  "WIPRO":      {security_id:"3787",  segment:"NSE_EQ"},
  "TATAMOTORS": {security_id:"3456",  segment:"NSE_EQ"},
  "BAJFINANCE": {security_id:"317",   segment:"NSE_EQ"},
};

export default function TerminalPage() {
  const qc = useQueryClient();
  const { accessToken, user } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const [liveData,   setLiveData]   = useState<Record<string, any>>({});
  const [wsStatus,   setWsStatus]   = useState<"connecting"|"live"|"polling">("connecting");
  const [lastUpdate, setLastUpdate] = useState<Date|null>(null);
  const [showAdd,    setShowAdd]    = useState(false);
  const [formulaRow, setFormulaRow] = useState<{id:string,symbol:string}|null>(null);
  const [showColumns, setShowColumns] = useState(false);
  const [orderPanel,  setOrderPanel]  = useState<{symbol:string,security_id:string,segment:string,prefillSide?:string,prefillPrice?:number}|null>(null);
  const wsRef = useRef<WebSocket|null>(null);

  // ── Watchlist (persisted to DB) ─────────────────────────────────────────────
  const { data: wlData } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get("/market/watchlist").then(r => r.data),
  });
  const watchlist: string[] = wlData?.symbols ?? [];
  const instrMap: Record<string,{security_id:string,segment:string}> = {};
  (wlData?.instruments ?? []).forEach((i: any) => {
    instrMap[i.symbol] = {security_id: i.security_id, segment: i.exchange_segment};
  });

  // ── Terminal rows (strategies/formulas with T/SL config) ───────────────────
  const { data: termRows } = useQuery({
    queryKey: ["terminal-rows"],
    queryFn: () => api.get("/terminal/rows").then(r => r.data),
    refetchInterval: 10_000,
  });

  // ── Account summary ────────────────────────────────────────────────────────
  const { data: funds } = useQuery({
    queryKey: ["dhan-funds"],
    queryFn: () => api.get("/market/funds").then(r => r.data),
    refetchInterval: 30_000,
  });

  // ── WebSocket live feed ────────────────────────────────────────────────────
  useEffect(() => {
    if (!accessToken) return;
    const wsBase = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000").replace(/^http/, "ws");
    const url    = `${wsBase}/api/ws/market?token=${accessToken}&symbols=ALL`;

    function connect() {
      setWsStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen    = () => setWsStatus("live");
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "ticks") {
            setLiveData(prev => {
              const next = {...prev};
              msg.data.forEach((q: any) => { next[q.symbol] = q; });
              return next;
            });
            setLastUpdate(new Date());
          }
        } catch {}
      };
      ws.onerror = () => setWsStatus("polling");
      ws.onclose = () => { setWsStatus("polling"); setTimeout(connect, 8000); };
    }
    connect();
    return () => wsRef.current?.close();
  }, [accessToken]);

  // ── REST fallback ──────────────────────────────────────────────────────────
  useQuery({
    queryKey: ["live-quotes-fallback"],
    queryFn: async () => {
      if (watchlist.length === 0) return [];
      const data = await api.get(`/market/live-quotes?symbols=${watchlist.join(",")}`).then(r => r.data);
      if (wsStatus !== "live") {
        const map: Record<string,any> = {};
        data.forEach((q: any) => { map[q.symbol] = q; });
        setLiveData(map);
        setLastUpdate(new Date());
      }
      return data;
    },
    refetchInterval: 4_000,
    enabled: wsStatus !== "live" && watchlist.length > 0,
  });

  // All columns (default + custom) from DB
  const { data: allCols, refetch: refetchCols } = useQuery({
    queryKey: ["terminal-columns"],
    queryFn: () => api.get("/terminal/columns").then(r => r.data),
  });
  const visibleCols = (allCols ?? [])
    .filter((c:any) => c.is_visible)
    .sort((a:any, b:any) => a.col_order - b.col_order);
  const customCols  = (allCols ?? []).filter((c:any) => c.col_type === "custom" && c.is_visible);

  // Live strategy signals — refreshed every 5s
  const { data: liveSignals } = useQuery({
    queryKey: ["live-signals"],
    queryFn: () => api.get("/strategies/live-signals").then(r => r.data),
    refetchInterval: 5000,
    enabled: watchlist.length > 0,
  });

  // Group signals by symbol → strategy
  const signalMap: Record<string, Record<string, any>> = {};
  (liveSignals ?? []).forEach((s: any) => {
    if (!signalMap[s.symbol]) signalMap[s.symbol] = {};
    signalMap[s.symbol][s.strategy_name] = s;
  });

  // Unique strategy names for column headers
  const strategyNames: string[] = [...new Set(
    (liveSignals ?? []).map((s: any) => s.strategy_name)
  )] as string[];


  const hideColMutation = useMutation({
    mutationFn: ({id, visible}: any) =>
      api.patch(`/terminal/columns/${id}/visibility`, {is_visible: visible}),
    onSuccess: () => refetchCols(),
  });

  const deleteColMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/terminal/columns/${id}`),
    onSuccess: () => { toast.success("Column removed"); refetchCols(); },
  });

  const resetColsMutation = useMutation({
    mutationFn: () => api.post("/terminal/columns/reset"),
    onSuccess: () => { toast.success("Columns reset to defaults"); refetchCols(); },
  });

  const removeMutation = useMutation({
    mutationFn: (sym: string) => api.delete(`/market/watchlist/${sym}`),
    onSuccess: () => { toast.success("Removed"); qc.invalidateQueries({queryKey:["watchlist"]}); },
  });

  const toggleRowMutation = useMutation({
    mutationFn: ({id, is_active}: any) => api.patch(`/terminal/rows/${id}/activate`, {is_active}),
    onSuccess: () => qc.invalidateQueries({queryKey:["terminal-rows"]}),
  });

  const exitRowMutation = useMutation({
    mutationFn: (id: string) => api.post(`/terminal/rows/${id}/exit`),
    onSuccess: () => { toast.success("Exit order sent"); qc.invalidateQueries({queryKey:["terminal-rows"]}); },
    onError: () => toast.error("No active position"),
  });


  const SECURITY_IDS = {
    "NIFTY50":   {security_id:"13",    segment:"IDX_I"},
    "BANKNIFTY": {security_id:"25",    segment:"IDX_I"},
    "RELIANCE":  {security_id:"2885",  segment:"NSE_EQ"},
    "TCS":       {security_id:"11536", segment:"NSE_EQ"},
    "INFY":      {security_id:"1594",  segment:"NSE_EQ"},
    "HDFCBANK":  {security_id:"1333",  segment:"NSE_EQ"},
    "ICICIBANK": {security_id:"4963",  segment:"NSE_EQ"},
    "SBIN":      {security_id:"3045",  segment:"NSE_EQ"},
    "WIPRO":     {security_id:"3787",  segment:"NSE_EQ"},
    "TATAMOTORS":{security_id:"3456",  segment:"NSE_EQ"},
    "BAJFINANCE":{security_id:"317",   segment:"NSE_EQ"},
  };
  const isLive = wsStatus === "live";

  // Build unified row list — watchlist symbols merged with terminal rows
  const termRowMap: Record<string, any> = {};
  (termRows ?? []).forEach((r: any) => { termRowMap[r.symbol] = r; });

  const overallPnl = (termRows ?? []).reduce((s: number, r: any) => s + (r.pnl ?? 0), 0);

  return (
    <Layout>
      {/* ── Account Summary Bar (Row 1 of Excel) ──────────────────────────── */}
      <div style={{
        display: "flex", gap: 0, marginBottom: 16,
        border: "1px solid var(--border)", background: "var(--surface)",
      }}>
        {[
          { label: "AVAIL BALANCE", value: funds?.availabelBalance != null ? `₹${Number(funds.availabelBalance).toLocaleString()}` : "—" },
          { label: "USED MARGIN",   value: funds?.utilizedAmount   != null ? `₹${Number(funds.utilizedAmount).toLocaleString()}`   : "—" },
          { label: "OVERALL P&L",   value: `${overallPnl >= 0 ? "+" : ""}₹${overallPnl.toLocaleString()}`,
            color: overallPnl >= 0 ? "var(--green)" : "var(--red)" },
        ].map(({label, value, color}) => (
          <div key={label} style={{
            flex: 1, padding: "12px 20px",
            borderRight: "1px solid var(--border)",
          }}>
            <div style={{fontSize: 9, letterSpacing: 2, color: "var(--muted)", marginBottom: 4}}>{label}</div>
            <div style={{fontSize: 18, fontWeight: 700, color: color ?? "var(--text)"}}>{value}</div>
          </div>
        ))}

        {/* Status + controls */}
        <div style={{display:"flex", alignItems:"center", gap:12, padding:"0 20px", marginLeft:"auto"}}>
          <div style={{display:"flex", alignItems:"center", gap:6,
            color: isLive ? "var(--green)" : "var(--muted)", fontSize: 11}}>
            <span style={{width:7, height:7, borderRadius:"50%", display:"inline-block",
              background: isLive ? "var(--green)" : "var(--muted)",
              boxShadow: isLive ? "0 0 6px var(--green)" : "none"}} />
            {isLive ? "LIVE" : "POLLING"}
          </div>
          {lastUpdate && <span style={{fontSize:10, color:"var(--muted)"}}>
            {lastUpdate.toLocaleTimeString()}
          </span>}
          {isAdmin && (
            <button className="exit-btn" style={{fontSize:11, padding:"6px 14px",
              color:"var(--yellow)", borderColor:"rgba(255,208,96,0.3)"}}
              onClick={() => setShowColumns(true)}>
              🔧 COLUMNS
            </button>
          )}
          <button className="connect-btn" style={{fontSize:11, padding:"6px 14px"}}
            onClick={() => { setShowAdd(v => !v); }}>
            {showAdd ? "✕ CANCEL" : "+ ADD SYMBOL"}
          </button>
        </div>
      </div>

      {/* ── Admin Formula Modal ─────────────────────────────────────────────── */}
      {isAdmin && formulaRow && (
        <AdminFormulaPanel
          rowId={formulaRow.id}
          symbol={formulaRow.symbol}
          onClose={() => setFormulaRow(null)}
        />
      )}

      {/* ── Column Manager Modal ──────────────────────────────────────────── */}
      {isAdmin && showColumns && (
        <AdminColumnManager onClose={() => setShowColumns(false)} />
      )}

      {orderPanel && (
        <OrderPanel
          symbol={orderPanel.symbol}
          securityId={orderPanel.securityId}
          segment={orderPanel.segment}
          ltp={liveData[orderPanel.symbol]?.ltp ?? null}
          onClose={() => setOrderPanel(null)}
          prefillSide={orderPanel.prefillSide}
          prefillPrice={orderPanel.prefillPrice}
        />
      )}

      {/* ── Add Symbol Panel ────────────────────────────────────────────────── */}
      {showAdd && (
        <AddSymbolPanel onAdded={() => {
          qc.invalidateQueries({queryKey:["watchlist"]});
          setShowAdd(false);
        }} />
      )}
      {/* ── Terminal Table ──────────────────────────────────────────────────── */}
      <TerminalTable onOrder={(sym, inst) => setOrderPanel({symbol:sym, ...inst})} instrMap={instrMap} signalMap={signalMap} strategyNames={strategyNames} watchlist={watchlist} liveData={liveData} termRowMap={termRowMap} visibleCols={visibleCols} isAdmin={isAdmin} onRemoveSymbol={(sym)=>removeMutation.mutate(sym)} onExitRow={(id)=>exitRowMutation.mutate(id)} onFormulaRow={(id,sym)=>setFormulaRow({id,symbol:sym})} onDeleteCol={(id)=>deleteColMutation.mutate(id)} />

      
      {/* ── Strategy Signal Table ──────────────────────────────────────────── */}
      {strategyNames.length > 0 && (
        <div style={{marginTop:16}}>
          <div style={{fontSize:10,letterSpacing:2,color:"var(--muted)",marginBottom:8,padding:"0 4px"}}>
            STRATEGY SIGNALS
          </div>
          <div style={{overflowX:"auto"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:12,fontFamily:"var(--font)"}}>
              <thead>
                <tr style={{background:"var(--surface)",borderBottom:"2px solid var(--border)"}}>
                  <th style={{padding:"8px 10px",fontSize:9,letterSpacing:1.5,color:"var(--muted)",
                    borderRight:"1px solid var(--border)",minWidth:140,textAlign:"left"}}>#  SYMBOL</th>
                  {strategyNames.map((name:string) => (
                    <th key={"sh-"+name} style={{
                      padding:"8px 12px",fontSize:9,letterSpacing:1.2,textAlign:"left",
                      color:"rgba(0,255,136,0.9)",whiteSpace:"nowrap",
                      borderRight:"1px solid var(--border)",minWidth:200,
                    }}>
                      <div>{name.toUpperCase()}</div>
                      <div style={{fontSize:8,color:"var(--muted)",fontWeight:400,marginTop:2}}>SIGNAL · ENTRY · SL · TARGET</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {watchlist.map((sym:string, idx:number) => (
                  <tr key={"strat-"+sym} style={{
                    borderBottom:"1px solid var(--border)",
                  }}
                    onMouseEnter={e=>(e.currentTarget.style.background="rgba(255,255,255,0.02)")}
                    onMouseLeave={e=>(e.currentTarget.style.background="transparent")}
                  >
                    <td style={{padding:"10px 10px",borderRight:"1px solid var(--border)"}}>
                      <div style={{fontSize:10,color:"var(--muted)",marginBottom:2}}>{idx+1}</div>
                      <div style={{fontWeight:700,color:"var(--green)",fontSize:12}}>{sym}</div>
                    </td>
                    {strategyNames.map((stratName:string) => {
                      const sig  = signalMap[sym]?.[stratName];
                      const dir  = sig?.direction || "HOLD";
                      const inst = instrMap[sym] || SECURITY_IDS[sym];
                      return (
                        <td key={"sc-"+stratName} style={{
                          padding:"10px 12px",
                          borderRight:"1px solid var(--border)",
                          minWidth:200,
                        }}>
                          {sig ? (
                            <div style={{display:"flex",flexDirection:"column",gap:6}}>
                              {/* Signal + Entry */}
                              <div style={{display:"flex",alignItems:"center",gap:8}}>
                                <span className={`badge ${dir==="BUY"?"badge-green":dir==="SELL"?"badge-red":"badge-gray"}`}
                                  style={{minWidth:48,textAlign:"center",fontSize:11}}>
                                  {dir}
                                </span>
                                {sig.price && (
                                  <span style={{fontSize:13,fontWeight:700}}>
                                    ₹{Number(sig.price).toLocaleString()}
                                  </span>
                                )}
                              </div>
                              {/* SL + Target */}
                              {(sig.sl || sig.target) && (
                                <div style={{display:"flex",gap:12,fontSize:11}}>
                                  {sig.sl && (
                                    <span style={{color:"var(--red)"}}>
                                      SL ₹{Number(sig.sl).toFixed(0)}
                                    </span>
                                  )}
                                  {sig.target && (
                                    <span style={{color:"var(--green)"}}>
                                      T ₹{Number(sig.target).toFixed(0)}
                                    </span>
                                  )}
                                </div>
                              )}
                              {/* Reason */}
                              {sig.reason && (
                                <div style={{fontSize:9,color:"var(--muted)",lineHeight:1.4}}>
                                  {sig.reason}
                                </div>
                              )}
                              {/* Action button */}
                              {dir !== "HOLD" && inst && (
                                <button
                                  onClick={()=>setOrderPanel({
                                    symbol:sym,...inst,
                                    prefillSide:dir,
                                    prefillPrice:sig.price||0,
                                  })}
                                  style={{
                                    padding:"5px 14px",fontSize:11,cursor:"pointer",
                                    fontWeight:700,fontFamily:"var(--font)",width:"fit-content",
                                    background:dir==="BUY"?"rgba(0,255,136,0.15)":"rgba(255,68,102,0.15)",
                                    border:`1px solid ${dir==="BUY"?"rgba(0,255,136,0.5)":"rgba(255,68,102,0.5)"}`,
                                    color:dir==="BUY"?"var(--green)":"var(--red)",
                                  }}>
                                  {dir} ORDER →
                                </button>
                              )}
                            </div>
                          ) : (
                            <div style={{color:"var(--muted)",fontSize:11}}>
                              <span className="badge badge-gray">HOLD</span>
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Bottom Summary ───────────────────────────────────────────────────── */}
      {watchlist.length > 0 && (
        <div style={{display:"flex", gap:0, marginTop:16,
          border:"1px solid var(--border)", background:"var(--surface)"}}>
          {[
            {label:"SYMBOLS",     value:watchlist.length},
            {label:"ACTIVE",      value:(termRows??[]).filter((r:any)=>r.is_active).length,
              color:"var(--green)"},
            {label:"IN POSITION", value:(termRows??[]).filter((r:any)=>r.status==="active").length,
              color:"var(--green)"},
            {label:"LIVE DATA",   value: isLive ? "● WEBSOCKET" : "○ POLLING",
              color: isLive ? "var(--green)" : "var(--muted)"},
          ].map(({label, value, color}) => (
            <div key={label} style={{flex:1, padding:"10px 20px",
              borderRight:"1px solid var(--border)"}}>
              <div style={{fontSize:9,letterSpacing:2,color:"var(--muted)",marginBottom:2}}>{label}</div>
              <div style={{fontSize:14,fontWeight:700,color:color??"var(--text)"}}>{value}</div>
            </div>
          ))}
        </div>
      )}
    </Layout>
  );
}

// ── Add Symbol Panel ──────────────────────────────────────────────────────────
function AddSymbolPanel({ onAdded }: { onAdded: () => void }) {
  const [query,   setQuery]   = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const addMutation = useMutation({
    mutationFn: (inst: any) => api.post("/market/watchlist", {
      symbol:           inst.symbol,
      security_id:      inst.security_id,
      exchange_segment: inst.segment,
    }),
    onSuccess: (_, inst) => { toast.success(`${inst.symbol} added`); onAdded(); },
  });

  useEffect(() => {
    if (query.length < 2) { setResults([]); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api.get(`/market/instruments/search?q=${query}`).then(r => r.data);
        setResults(data);
      } catch {}
      setLoading(false);
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="card" style={{marginBottom:12}}>
      <div style={{padding:"14px 16px"}}>
        <div style={{position:"relative", maxWidth:500, display:"flex", gap:8}}>
          <input className="field-input" value={query}
            onChange={e => setQuery(e.target.value)} autoFocus
            placeholder="Search symbol or company... e.g. HDFC, Zomato, TCS"
            style={{flex:1}} />
          {loading && <span style={{position:"absolute", right:12, top:"50%",
            transform:"translateY(-50%)", color:"var(--muted)", fontSize:11}}>...</span>}
        </div>
        {results.length > 0 && (
          <div style={{marginTop:6, border:"1px solid var(--border)",
            background:"var(--surface)", maxHeight:240, overflowY:"auto", maxWidth:500}}>
            {results.map(inst => (
              <div key={inst.security_id}
                style={{padding:"8px 12px", display:"flex", justifyContent:"space-between",
                  alignItems:"center", borderBottom:"1px solid var(--border)", cursor:"pointer"}}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--green-dim)")}
                onMouseLeave={e => (e.currentTarget.style.background = "")}>
                <div>
                  <span style={{fontWeight:700, color:"var(--green)", fontSize:12}}>{inst.symbol}</span>
                  <span style={{fontSize:10, color:"var(--muted)", marginLeft:8}}>{inst.name}</span>
                </div>
                <div style={{display:"flex", gap:8, alignItems:"center"}}>
                  <span style={{fontSize:9, color:"var(--muted)"}}>{inst.exchange} · {inst.series}</span>
                  <button className="connect-btn" style={{padding:"2px 10px", fontSize:10}}
                    onClick={() => addMutation.mutate(inst)}
                    disabled={addMutation.isPending}>+ ADD</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


// ── Admin Formula Panel ───────────────────────────────────────────────────────
export function AdminFormulaPanel({ rowId, symbol, onClose }: {
  rowId: string; symbol: string; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    entry_formula:  "",
    exit_formula:   "",
    target_formula: "",
    sl_formula:     "",
    trail_pct:      "",
    strategy_label: "",
  });
  const set = (k: string) => (e: any) => setForm(f => ({...f, [k]: e.target.value}));

  const { data: current } = useQuery({
    queryKey: ["row-formula", rowId],
    queryFn: () => api.get(`/terminal/rows/${rowId}/formula`).then(r => r.data),
    onSuccess: (d: any) => setForm({
      entry_formula:  d.entry_formula  ?? "",
      exit_formula:   d.exit_formula   ?? "",
      target_formula: "",
      sl_formula:     "",
      trail_pct:      d.trail_pct      ?? "",
      strategy_label: d.strategy_label ?? "",
    }),
  } as any);

  const { data: presets } = useQuery({
    queryKey: ["formula-presets"],
    queryFn: () => api.get("/terminal/formula-presets").then(r => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: () => api.put(`/terminal/rows/${rowId}/formula`, {
      entry_formula:  form.entry_formula  || null,
      exit_formula:   form.exit_formula   || null,
      trail_pct:      form.trail_pct      ? parseFloat(form.trail_pct) : null,
      strategy_label: form.strategy_label || null,
    }),
    onSuccess: () => {
      toast.success(`Formula saved for ${symbol}`);
      qc.invalidateQueries({queryKey: ["terminal-rows"]});
      onClose();
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Save failed"),
  });

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.8)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        padding: 24, width: 560, maxHeight: "90vh", overflowY: "auto",
      }}>
        {/* Header */}
        <div style={{display:"flex", justifyContent:"space-between", marginBottom:20}}>
          <div>
            <div style={{fontSize:14, fontWeight:700, color:"var(--green)"}}>
              🔒 FORMULA CONFIG
            </div>
            <div style={{fontSize:11, color:"var(--muted)"}}>
              {symbol} — Admin only · Hidden from users
            </div>
          </div>
          <button onClick={onClose}
            style={{background:"transparent",border:"none",color:"var(--muted)",
              cursor:"pointer",fontSize:18}}>✕</button>
        </div>

        {/* Preset shortcuts */}
        <div style={{marginBottom:16}}>
          <div style={{fontSize:10, letterSpacing:2, color:"var(--muted)", marginBottom:8}}>
            BUILT-IN STRATEGIES
          </div>
          <div style={{display:"flex", gap:6, flexWrap:"wrap"}}>
            {(presets ?? []).filter((p: any) => p.shortcut !== "custom").map((p: any) => (
              <button key={p.shortcut}
                onClick={() => setForm(f => ({
                  ...f,
                  entry_formula:  p.shortcut,
                  strategy_label: f.strategy_label || p.name,
                }))}
                style={{
                  padding: "5px 10px", fontSize: 10, cursor: "pointer",
                  fontFamily: "var(--font)",
                  background: form.entry_formula === p.shortcut
                    ? "var(--green-dim)" : "transparent",
                  border: `1px solid ${form.entry_formula === p.shortcut
                    ? "rgba(0,255,136,0.4)" : "var(--border)"}`,
                  color: form.entry_formula === p.shortcut
                    ? "var(--green)" : "var(--muted)",
                }}
                title={p.description}>
                {p.name.split(" ").slice(0,3).join(" ")}
              </button>
            ))}
          </div>
        </div>

        {/* Formula fields */}
        <div style={{display:"flex", flexDirection:"column", gap:12}}>
          <div className="field">
            <label className="field-label" style={{color:"var(--yellow)"}}>
              ENTRY FORMULA (hidden from users)
            </label>
            <input className="field-input" value={form.entry_formula}
              onChange={set("entry_formula")}
              placeholder="@ORFib  or  @MACross(9,21)  or  ltp > ma(20) AND rsi(14) < 70" />
            <div style={{fontSize:10, color:"var(--muted)", marginTop:4}}>
              Built-ins: @ORFib · @ORFib(trail=0.3) · @MACross(9,21) · @RSI(14,30,70) · @VWAP
            </div>
          </div>

          <div className="field">
            <label className="field-label" style={{color:"var(--yellow)"}}>
              EXIT FORMULA (optional)
            </label>
            <input className="field-input" value={form.exit_formula}
              onChange={set("exit_formula")}
              placeholder="e.g. ma(9) < ma(21)  (leave blank for T/SL only)" />
          </div>

          <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12}}>
            <div className="field">
              <label className="field-label">TRAIL SL %</label>
              <input className="field-input" type="number" value={form.trail_pct}
                onChange={set("trail_pct")} placeholder="e.g. 0.3" />
            </div>
            <div className="field">
              <label className="field-label">LABEL (shown to users)</label>
              <input className="field-input" value={form.strategy_label}
                onChange={set("strategy_label")}
                placeholder="e.g. ORFib Strategy" />
              <div style={{fontSize:10, color:"var(--muted)", marginTop:4}}>
                Users see this label — not the formula
              </div>
            </div>
          </div>

          {/* Preview what user sees */}
          <div style={{
            padding:"12px 14px", background:"rgba(0,255,136,0.05)",
            border:"1px solid rgba(0,255,136,0.2)",
          }}>
            <div style={{fontSize:10, letterSpacing:1.5, color:"var(--green)", marginBottom:6}}>
              WHAT USERS WILL SEE
            </div>
            <div style={{fontSize:12}}>
              <span style={{color:"var(--text)"}}>Symbol: </span>
              <span style={{color:"var(--green)", fontWeight:700}}>{symbol}</span>
              <span style={{color:"var(--muted)", marginLeft:12}}>
                Strategy: {form.strategy_label || "—"}
              </span>
            </div>
            <div style={{fontSize:11, color:"var(--muted)", marginTop:4}}>
              Signal, entry price, target and SL will be auto-calculated and shown
              in the terminal table. The formula itself is never visible to users.
            </div>
          </div>
        </div>

        <div style={{display:"flex", gap:12, marginTop:20}}>
          <button className={`auth-btn${saveMutation.isPending?" loading":""}`}
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            style={{maxWidth:180}}>
            {saveMutation.isPending ? "SAVING..." : "SAVE FORMULA →"}
          </button>
          <button className="exit-btn" onClick={onClose} style={{padding:"12px 20px"}}>
            CANCEL
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Admin Column Manager ──────────────────────────────────────────────────────
export function AdminColumnManager({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: "", formula: "", col_order: 0,
    width: 80, color_rules: "",
  });
  const [editId,    setEditId]    = useState<string|null>(null);
  const [validMsg,  setValidMsg]  = useState("");
  const [validOk,   setValidOk]   = useState<boolean|null>(null);
  const set = (k: string) => (e: any) => setForm(f => ({...f, [k]: e.target.value}));

  const { data: columns } = useQuery({
    queryKey: ["terminal-columns"],
    queryFn: () => api.get("/terminal/columns").then(r => r.data),
  });

  const validateMutation = useMutation({
    mutationFn: (formula: string) =>
      api.post("/terminal/columns/validate", { formula }).then(r => r.data),
    onSuccess: (d: any) => { setValidMsg(d.message); setValidOk(d.valid); },
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        name:        form.name,
        formula:     form.formula,
        col_order:   parseInt(String(form.col_order)),
        width:       parseInt(String(form.width)),
        is_visible:  true,
        color_rules: form.color_rules || null,
      };
      return editId
        ? api.put(`/terminal/columns/${editId}`, payload)
        : api.post("/terminal/columns", payload);
    },
    onSuccess: () => {
      toast.success(editId ? "Column updated" : "Column added");
      qc.invalidateQueries({queryKey:["terminal-columns"]});
      setForm({name:"",formula:"",col_order:0,width:80,color_rules:""});
      setEditId(null); setValidMsg(""); setValidOk(null);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/terminal/columns/${id}`),
    onSuccess: () => {
      toast.success("Column deleted");
      qc.invalidateQueries({queryKey:["terminal-columns"]});
    },
  });

  function startEdit(col: any) {
    setEditId(col.id);
    setForm({
      name: col.name, formula: col.formula ?? "",
      col_order: col.col_order, width: col.width,
      color_rules: col.color_rules ?? "",
    });
    setValidMsg(""); setValidOk(null);
  }

  const EXAMPLES = [
    { name:"TREND",  formula:'=IF((C4+D4+E4)/3>K4,"DOWN","UP")',          colors:'{"UP":"green","DOWN":"red"}' },
    { name:"HCG",    formula:"=ROUND(C4-E4,2)",                            colors:'{"positive":"green","negative":"red"}' },
    { name:"OCG",    formula:"=ROUND(B4-E4,2)",                            colors:'{"positive":"green","negative":"red"}' },
    { name:"LCG",    formula:"=ROUND(E4-D4,2)",                            colors:'{"positive":"green","negative":"red"}' },
    { name:"KD",     formula:"=ROUND((close-low)/(high-low)*100,2)",             colors:'{}' },
  ];

  return (
    <div style={{
      position:"fixed", top:0, left:0, right:0, bottom:0,
      background:"rgba(0,0,0,0.85)", zIndex:1000,
      display:"flex", alignItems:"center", justifyContent:"center",
    }}>
      <div style={{
        background:"var(--surface)", border:"1px solid var(--border)",
        width:680, maxHeight:"92vh", overflowY:"auto",
      }}>
        {/* Header */}
        <div style={{
          padding:"16px 20px", borderBottom:"1px solid var(--border)",
          display:"flex", justifyContent:"space-between", alignItems:"center",
        }}>
          <div>
            <div style={{fontSize:14, fontWeight:700, color:"var(--green)"}}>
              🔒 FORMULA COLUMNS
            </div>
            <div style={{fontSize:11, color:"var(--muted)"}}>
              Admin only — users see calculated values, never the formula
            </div>
          </div>
          <button onClick={onClose}
            style={{background:"transparent",border:"none",
              color:"var(--muted)",cursor:"pointer",fontSize:18}}>✕</button>
        </div>

        <div style={{padding:"20px"}}>
          {/* Example templates */}
          <div style={{marginBottom:16}}>
            <div style={{fontSize:10,letterSpacing:2,color:"var(--muted)",marginBottom:8}}>
              QUICK TEMPLATES (click to load)
            </div>
            <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
              {EXAMPLES.map(ex => (
                <button key={ex.name}
                  onClick={() => setForm(f => ({...f, name:ex.name,
                    formula:ex.formula, color_rules:ex.colors}))}
                  style={{
                    padding:"5px 12px", fontSize:11, cursor:"pointer",
                    fontFamily:"var(--font)", background:"transparent",
                    border:"1px solid var(--border)", color:"var(--muted)",
                    transition:"all 0.15s",
                  }}
                  onMouseEnter={e=>{
                    (e.target as any).style.color="var(--green)";
                    (e.target as any).style.borderColor="rgba(0,255,136,0.4)";
                  }}
                  onMouseLeave={e=>{
                    (e.target as any).style.color="var(--muted)";
                    (e.target as any).style.borderColor="var(--border)";
                  }}>
                  {ex.name}
                </button>
              ))}
            </div>
          </div>

          {/* Formula form */}
          <div style={{
            padding:"16px", border:"1px solid var(--border)",
            background:"rgba(0,0,0,0.2)", marginBottom:16,
          }}>
            <div style={{fontSize:11,fontWeight:700,color:"var(--green)",marginBottom:12}}>
              {editId ? "EDIT COLUMN" : "ADD NEW COLUMN"}
            </div>

            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>
              <div className="field">
                <label className="field-label">COLUMN NAME</label>
                <input className="field-input" value={form.name}
                  onChange={set("name")} placeholder="e.g. TREND" />
              </div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
                <div className="field">
                  <label className="field-label">ORDER</label>
                  <input className="field-input" type="number"
                    value={form.col_order} onChange={set("col_order")} />
                </div>
                <div className="field">
                  <label className="field-label">WIDTH (px)</label>
                  <input className="field-input" type="number"
                    value={form.width} onChange={set("width")} />
                </div>
              </div>
            </div>

            <div className="field" style={{marginBottom:8}}>
              <label className="field-label" style={{color:"var(--yellow)"}}>
                FORMULA (Excel syntax — hidden from users)
              </label>
              <input className="field-input" value={form.formula}
                onChange={set("formula")}
                placeholder='Named: =IF((high+low+close)/3>ltp,"DOWN","UP")  or Excel: =IF((C4+D4+E4)/3>K4,"DOWN","UP")' />
              <div style={{fontSize:10,color:"var(--muted)",marginTop:4}}>
                <strong style={{color:"var(--green)"}}>Named (recommended):</strong> open, high, low, close, vwap, ltp, volume, oi, bp1, sp1
                &nbsp;·&nbsp;
                <strong style={{color:"var(--muted)"}}>Excel refs:</strong> B=Open C=High D=Low E=Close F=VWAP K=LTP I=Volume J=OI
              </div>
            </div>

            {/* Validate button */}
            <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:12}}>
              <button
                onClick={() => validateMutation.mutate(form.formula)}
                disabled={!form.formula || validateMutation.isPending}
                style={{
                  padding:"6px 14px", fontSize:11, cursor:"pointer",
                  fontFamily:"var(--font)",
                  background:"transparent",
                  border:"1px solid var(--border)",
                  color:"var(--muted)",
                }}>
                {validateMutation.isPending ? "..." : "✓ VALIDATE"}
              </button>
              {validMsg && (
                <span style={{
                  fontSize:11,
                  color: validOk ? "var(--green)" : "var(--red)",
                }}>
                  {validOk ? "✓ " : "✗ "}{validMsg}
                </span>
              )}
            </div>

            <div className="field" style={{marginBottom:12}}>
              <label className="field-label">COLOR RULES (JSON — optional)</label>
              <input className="field-input" value={form.color_rules}
                onChange={set("color_rules")}
                placeholder='{"UP":"green","DOWN":"red"} or {"positive":"green","negative":"red"}' />
              <div style={{fontSize:10,color:"var(--muted)",marginTop:4}}>
                Maps output values to colors: green, red, yellow, muted
              </div>
            </div>

            <div style={{display:"flex",gap:8}}>
              <button
                className={`auth-btn${saveMutation.isPending?" loading":""}`}
                onClick={() => saveMutation.mutate()}
                disabled={!form.name || !form.formula || saveMutation.isPending}
                style={{maxWidth:180}}>
                {saveMutation.isPending ? "SAVING..." : editId ? "UPDATE →" : "ADD COLUMN →"}
              </button>
              {editId && (
                <button className="exit-btn"
                  onClick={() => {
                    setEditId(null);
                    setForm({name:"",formula:"",col_order:0,width:80,color_rules:""});
                    setValidMsg(""); setValidOk(null);
                  }}
                  style={{padding:"10px 16px"}}>CANCEL</button>
              )}
            </div>
          </div>

          {/* All columns list with show/hide/delete */}
          {columns && columns.length > 0 && (
            <div>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
                <div style={{fontSize:10,letterSpacing:2,color:"var(--muted)"}}>
                  ALL COLUMNS ({columns.length}) — click ✕ to remove, eye to show/hide
                </div>
                <button
                  onClick={() => { if(confirm("Reset all columns to defaults?")) api.post("/terminal/columns/reset").then(()=>{toast.success("Reset");qc.invalidateQueries({queryKey:["terminal-columns"]});}).catch(()=>toast.error("Failed")); }}
                  style={{padding:"4px 12px",fontSize:10,cursor:"pointer",
                    background:"transparent",border:"1px solid var(--border)",
                    color:"var(--muted)",fontFamily:"var(--font)"}}>
                  ↺ RESET DEFAULTS
                </button>
              </div>
              <div style={{display:"flex",flexWrap:"wrap",gap:6}}>
                {columns.map((col: any) => (
                  <div key={col.id} style={{
                    display:"flex",alignItems:"center",gap:4,
                    padding:"5px 10px",
                    background: col.is_visible
                      ? col.col_type==="custom"?"rgba(255,208,96,0.08)":"rgba(0,255,136,0.05)"
                      : "rgba(74,85,104,0.1)",
                    border:`1px solid ${col.is_visible
                      ? col.col_type==="custom"?"rgba(255,208,96,0.3)":"rgba(0,255,136,0.2)"
                      : "var(--border)"}`,
                    opacity: col.is_visible ? 1 : 0.5,
                  }}>
                    <span style={{
                      fontSize:11,fontWeight:700,
                      color: col.col_type==="custom"?"var(--yellow)":"var(--text)",
                    }}>{col.name}</span>
                    {col.col_type==="custom"&&<span style={{fontSize:9,color:"var(--muted)"}}>ƒ</span>}
                    {col.col_type==="custom"&&col.formula&&(
                      <button className="exit-btn"
                        style={{padding:"1px 6px",fontSize:9,marginLeft:2}}
                        onClick={() => startEdit(col)}>EDIT</button>
                    )}
                    <button
                      onClick={() => api.patch(`/terminal/columns/${col.id}/visibility`,
                        {is_visible: !col.is_visible})
                        .then(()=>qc.invalidateQueries({queryKey:["terminal-columns"]}))}
                      title={col.is_visible ? "Hide" : "Show"}
                      style={{background:"transparent",border:"none",
                        color:col.is_visible?"var(--green)":"var(--muted)",
                        cursor:"pointer",fontSize:11,padding:0}}>
                      {col.is_visible ? "👁" : "🚫"}
                    </button>
                    <button
                      onClick={() => { if(confirm(`Remove "${col.name}" column?`)) deleteMutation.mutate(col.id); }}
                      title="Remove column"
                      style={{background:"transparent",border:"none",
                        color:"rgba(255,68,102,0.5)",cursor:"pointer",
                        fontSize:10,padding:0}}>✕</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(!columns || columns.length === 0) && (
            <div style={{color:"var(--muted)",fontSize:12,textAlign:"center",padding:20}}>
              No columns yet. Click ↺ RESET DEFAULTS to restore default columns.
              <br/>
              <button className="connect-btn" style={{marginTop:10}}
                onClick={()=>api.post("/terminal/columns/reset").then(()=>{toast.success("Seeded");qc.invalidateQueries({queryKey:["terminal-columns"]});})}>
                ↺ SEED DEFAULTS
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Terminal Table ────────────────────────────────────────────────────────────
function TerminalTable({ watchlist, liveData, termRowMap, visibleCols, isAdmin,
  onRemoveSymbol, onExitRow, onFormulaRow, onDeleteCol, onOrder, instrMap, signalMap, strategyNames }: {
  watchlist: string[]; liveData: Record<string,any>; termRowMap: Record<string,any>;
  visibleCols: any[]; isAdmin: boolean;
  onRemoveSymbol:(s:string)=>void; onExitRow:(id:string)=>void;
  onFormulaRow:(id:string,sym:string)=>void; onDeleteCol:(id:string)=>void;
  onOrder:(sym:string,inst:{security_id:string,segment:string})=>void;
  instrMap: Record<string,{security_id:string,segment:string}>;
  signalMap: Record<string,Record<string,any>>;
  strategyNames: string[];
}) {
  if (watchlist.length === 0) return (
    <div style={{padding:"60px 20px",textAlign:"center",color:"var(--muted)",
      fontSize:13,border:"1px solid var(--border)",background:"var(--surface)"}}>
      No symbols — click <strong style={{color:"var(--green)"}}>+ ADD SYMBOL</strong> to start
    </div>
  );

  return (
    <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontSize:13,fontFamily:"var(--font)"}}>
        <thead>
          <tr style={{background:"var(--surface)",borderBottom:"2px solid var(--border)"}}>
            <th style={{padding:"8px 10px",fontSize:10,letterSpacing:1.5,color:"var(--muted)",
              borderRight:"1px solid var(--border)",minWidth:30}}>#</th>
            <th style={{padding:"8px 10px",fontSize:10,letterSpacing:1.5,color:"var(--muted)",
              borderRight:"1px solid var(--border)",minWidth:140,textAlign:"left"}}>SYMBOL</th>
            {visibleCols.map((col:any) => (
              <th key={col.id} style={{
                padding:"8px 8px",fontSize:10,letterSpacing:1.5,whiteSpace:"nowrap",
                color:col.col_type==="custom"||col.col_type==="formula"?"var(--yellow)":"var(--muted)",
                borderRight:"1px solid var(--border)",minWidth:col.width||80,textAlign:"left",
              }}>
                <div style={{display:"flex",alignItems:"center",gap:3}}>
                  <span>{col.name}</span>
                  <button onClick={()=>onDeleteCol(col.id)} title="Remove column"
                    style={{background:"transparent",border:"none",
                      color:"rgba(255,68,102,0.4)",cursor:"pointer",
                      fontSize:9,padding:0,lineHeight:1,opacity:0.6}}>✕</button>
                </div>
              </th>
            ))}
            <th style={{padding:"8px 6px",fontSize:9,color:"var(--muted)",minWidth:90}}></th>
          </tr>
        </thead>
        <tbody>
          {watchlist.map((sym, idx) => {
            const live  = liveData[sym] ?? {};
            const trow  = termRowMap[sym];
            const ltp   = live.ltp ?? trow?.ltp ?? null;
            const chg   = live.change_pct ?? null;
            const pos   = (chg ?? 0) >= 0;
            const inPos = trow?.status === "active";
            const pnl   = trow?.pnl ?? null;
            const tick  = { ...live, ltp: ltp ?? 0 };

            // Pre-evaluate formula cols for cross-refs
            const colValues: Record<string,any> = {};
            visibleCols.forEach((c:any) => {
              if ((c.col_type==="custom"||c.col_type==="formula") && c.formula) {
                const v = evalExcelFormula(c.formula, tick);
                if (v != null) colValues[c.name] = v;
              }
            });

            function getCellValue(col: any): {color:string, formatted:string} {
              let value: any = null;
              let color = "var(--text)";

              if ((col.col_type==="custom"||col.col_type==="formula") && col.formula) {
                value = evalExcelFormula(col.formula, tick, colValues);
                color = getColColor(value, col.color_rules);
              } else {
                switch(col.col_key) {
                  case "open":       value=live.open; break;
                  case "high":       value=live.high; color="var(--green)"; break;
                  case "low":        value=live.low;  color="var(--red)"; break;
                  case "close":      value=live.close; break;
                  case "vwap":       value=live.vwap||live.atp||null; break;
                  case "bp1":        value=live.bp1; color="var(--green)"; break;
                  case "sp1":        value=live.sp1; color="var(--red)"; break;
                  case "volume":     value=live.volume; break;
                  case "oi":         value=live.oi; break;
                  case "ltp":        value=ltp; break;
                  case "change_pct": value=chg; color=pos?"var(--green)":"var(--red)"; break;
                  case "quantity":   value=trow?.quantity; break;
                  case "entry_price":value=trow?.entry_price; break;
                  case "target":     value=trow?.current_target; color="var(--green)"; break;
                  case "sl":         value=trow?.current_sl; color="var(--red)"; break;
                  case "pnl":        value=pnl; color=pnl==null?"var(--muted)":pnl>=0?"var(--green)":"var(--red)"; break;
                }
                if (col.color_rules) color = getColColor(value, col.color_rules);
              }

              let formatted = "—";
              if (value != null && value !== "") {
                if (col.col_key==="volume"||col.col_key==="oi") {
                  formatted = Number(value)>0 ? (Number(value)/100000).toFixed(1)+"L" : "—";
                } else if (col.col_key==="change_pct") {
                  formatted = `${pos?"+":""}${Number(value).toFixed(2)}%`;
                } else if (typeof value==="number" && col.col_key!=="quantity") {
                  formatted = `₹${Number(value).toLocaleString()}`;
                } else {
                  formatted = String(value);
                }
              }
              return {color, formatted};
            }

            return (
              <tr key={sym} style={{
                borderBottom:"1px solid var(--border)",
                background:inPos?"rgba(0,255,136,0.03)":"transparent",
                borderLeft:inPos?"2px solid var(--green)":"2px solid transparent",
              }}
                onMouseEnter={e=>(e.currentTarget.style.background=inPos?"rgba(0,255,136,0.06)":"rgba(255,255,255,0.02)")}
                onMouseLeave={e=>(e.currentTarget.style.background=inPos?"rgba(0,255,136,0.03)":"transparent")}
              >
                <td style={{padding:"6px 10px",fontSize:12,color:"var(--muted)",
                  borderRight:"1px solid var(--border)",textAlign:"center",fontWeight:600}}>
                  {idx+1}
                </td>
                <td style={{padding:"6px 10px",borderRight:"1px solid var(--border)"}}>
                  <div style={{fontWeight:700,color:"var(--green)",fontSize:13}}>{sym}</div>
                  <div style={{fontSize:10,color:"var(--muted)"}}>{trow?.strategy_label??"WATCHLIST"}</div>
                </td>
                {visibleCols.map((col:any) => {
                  const {color, formatted} = getCellValue(col);
                  return (
                    <td key={col.id} style={{
                      padding:"7px 10px", color,
                      borderRight:"1px solid var(--border)",
                      fontWeight:col.col_key==="ltp"?"700":"400",
                      fontSize:col.col_key==="ltp"?"14px":"13px",
                    }}>
                      {formatted}
                    </td>
                  );
                })}
                <td style={{padding:"6px 8px"}}>
                  <div style={{display:"flex",gap:4}}>
                    {inPos&&trow&&(
                      <button className="exit-btn"
                        style={{padding:"2px 7px",fontSize:10,color:"var(--red)",
                          borderColor:"rgba(255,68,102,0.4)"}}
                        onClick={()=>onExitRow(trow.id)}>EXIT</button>
                    )}
                    {(() => {
                        const inst = (typeof instrMap !== "undefined" ? instrMap[sym] : null) || SECURITY_IDS[sym];
                        if (!inst) return null;
                        return <>
                          <button onClick={e=>{e.stopPropagation();onOrder(sym, inst);}}
                            style={{padding:"2px 8px",fontSize:10,cursor:"pointer",fontWeight:700,
                              background:"rgba(0,255,136,0.1)",border:"1px solid rgba(0,255,136,0.3)",
                              color:"var(--green)",fontFamily:"var(--font)"}}>B</button>
                          <button onClick={e=>{e.stopPropagation();onOrder(sym, inst);}}
                            style={{padding:"2px 8px",fontSize:10,cursor:"pointer",fontWeight:700,
                              background:"rgba(255,68,102,0.1)",border:"1px solid rgba(255,68,102,0.3)",
                              color:"var(--red)",fontFamily:"var(--font)"}}>S</button>
                        </>;
                      })()}
                      {isAdmin&&trow&&(
                      <button onClick={()=>onFormulaRow(trow.id,sym)}
                        style={{padding:"2px 5px",fontSize:10,cursor:"pointer",
                          background:"rgba(255,208,96,0.1)",border:"1px solid rgba(255,208,96,0.3)",
                          color:"var(--yellow)",fontFamily:"var(--font)"}}
                        title="Set strategy formula">🔒</button>
                    )}
                    <button onClick={()=>onRemoveSymbol(sym)}
                      style={{padding:"2px 5px",fontSize:11,background:"transparent",
                        border:"none",color:"var(--muted)",cursor:"pointer",opacity:0.5}}>✕</button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Order Panel (BUY/SELL) ────────────────────────────────────────────────────
function OrderPanel({ symbol, securityId, segment, ltp, onClose, prefillSide, prefillPrice }: {
  symbol: string; securityId: string; segment: string;
  ltp: number | null; onClose: () => void;
  prefillSide?: string; prefillPrice?: number;
}) {
  const qc = useQueryClient();
  const [side,     setSide]     = useState<"BUY"|"SELL">((prefillSide as any) || "BUY");
  const [qty,      setQty]      = useState("1");
  const [orderType,setOrderType]= useState<"MARKET"|"LIMIT">("MARKET");
  const [product,  setProduct]  = useState<"INTRADAY"|"CNC">("INTRADAY");
  const [price,    setPrice]    = useState(prefillPrice ? String(prefillPrice) : "");
  const [confirm,  setConfirm]  = useState(false);

  const orderMutation = useMutation({
    mutationFn: () => api.post("/terminal/order", {
      symbol,
      security_id:      securityId,
      exchange_segment: segment,
      transaction_type: side,
      quantity:         parseInt(qty),
      order_type:       orderType,
      product_type:     product,
      price:            orderType === "LIMIT" ? parseFloat(price) : 0,
    }),
    onSuccess: (res: any) => {
      toast.success(`✅ ${side} order placed — ID: ${res.data?.order_id}`);
      qc.invalidateQueries({queryKey:["orderbook"]});
      onClose();
    },
    onError: (e: any) => { const d = e.response?.data?.detail; const msg = Array.isArray(d) ? d.map((x:any) => x.msg || JSON.stringify(x)).join(", ") : typeof d === "string" ? d : d?.error_message || JSON.stringify(d) || "Order failed"; toast.error(msg); setConfirm(false); },
  });

  const estimatedValue = ltp && qty ? (ltp * parseInt(qty || "0")).toLocaleString() : "—";

  return (
    <div style={{
      position:"fixed", top:0, left:0, right:0, bottom:0,
      background:"rgba(0,0,0,0.85)", zIndex:1000,
      display:"flex", alignItems:"center", justifyContent:"center",
    }}>
      <div style={{
        background:"var(--surface)", border:"1px solid var(--border)",
        width:420, padding:0, overflow:"hidden",
      }}>
        {/* Header */}
        <div style={{
          padding:"14px 20px",
          background: side==="BUY" ? "rgba(0,255,136,0.1)" : "rgba(255,68,102,0.1)",
          borderBottom:"1px solid var(--border)",
          display:"flex", justifyContent:"space-between", alignItems:"center",
        }}>
          <div>
            <span style={{
              fontSize:16, fontWeight:700,
              color: side==="BUY" ? "var(--green)" : "var(--red)",
            }}>{side} ORDER</span>
            <span style={{fontSize:13, color:"var(--text)", marginLeft:10, fontWeight:700}}>{symbol}</span>
          </div>
          <button onClick={onClose} style={{
            background:"transparent", border:"none",
            color:"var(--muted)", cursor:"pointer", fontSize:18,
          }}>✕</button>
        </div>

        <div style={{padding:"20px"}}>
          {/* BUY / SELL toggle */}
          <div style={{display:"flex", marginBottom:16}}>
            {(["BUY","SELL"] as const).map(s => (
              <button key={s} onClick={() => setSide(s)} style={{
                flex:1, padding:"10px", fontSize:12, fontWeight:700,
                cursor:"pointer", fontFamily:"var(--font)",
                border:"1px solid",
                background: side===s
                  ? s==="BUY" ? "rgba(0,255,136,0.15)" : "rgba(255,68,102,0.15)"
                  : "transparent",
                borderColor: side===s
                  ? s==="BUY" ? "rgba(0,255,136,0.5)" : "rgba(255,68,102,0.5)"
                  : "var(--border)",
                color: side===s
                  ? s==="BUY" ? "var(--green)" : "var(--red)"
                  : "var(--muted)",
                borderRight: s==="BUY" ? "none" : undefined,
              }}>{s}</button>
            ))}
          </div>

          {/* LTP */}
          {ltp && (
            <div style={{
              padding:"8px 12px", marginBottom:16,
              background:"rgba(255,255,255,0.03)",
              border:"1px solid var(--border)",
              display:"flex", justifyContent:"space-between",
            }}>
              <span style={{fontSize:11, color:"var(--muted)"}}>LTP</span>
              <span style={{fontSize:14, fontWeight:700}}>₹{Number(ltp).toLocaleString()}</span>
            </div>
          )}

          {/* Order Type + Product */}
          <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:12}}>
            <div className="field">
              <label className="field-label">ORDER TYPE</label>
              <select className="field-input" value={orderType}
                onChange={e => setOrderType(e.target.value as any)}
                style={{background:"var(--surface)", color:"var(--text)", fontFamily:"var(--font)"}}>
                <option value="MARKET">MARKET</option>
                <option value="LIMIT">LIMIT</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">PRODUCT</label>
              <select className="field-input" value={product}
                onChange={e => setProduct(e.target.value as any)}
                style={{background:"var(--surface)", color:"var(--text)", fontFamily:"var(--font)"}}>
                <option value="INTRADAY">INTRADAY (MIS)</option>
                <option value="CNC">CNC (Delivery)</option>
              </select>
            </div>
          </div>

          {/* Quantity + Price */}
          <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:16}}>
            <div className="field">
              <label className="field-label">QUANTITY</label>
              <input className="field-input" type="number" min="1"
                value={qty} onChange={e => setQty(e.target.value)} />
            </div>
            {orderType === "LIMIT" && (
              <div className="field">
                <label className="field-label">PRICE (₹)</label>
                <input className="field-input" type="number" step="0.05"
                  value={price} onChange={e => setPrice(e.target.value)}
                  placeholder={ltp ? String(ltp) : "0.00"} />
              </div>
            )}
          </div>

          {/* Order summary */}
          <div style={{
            padding:"10px 12px", marginBottom:16,
            background:"rgba(255,255,255,0.02)",
            border:"1px solid var(--border)", fontSize:11,
          }}>
            <div style={{display:"flex", justifyContent:"space-between", marginBottom:4}}>
              <span style={{color:"var(--muted)"}}>Est. Value</span>
              <span style={{fontWeight:700}}>₹{estimatedValue}</span>
            </div>
            <div style={{display:"flex", justifyContent:"space-between"}}>
              <span style={{color:"var(--muted)"}}>Exchange</span>
              <span>{segment}</span>
            </div>
          </div>

          {/* Confirm step */}
          {!confirm ? (
            <button
              onClick={() => setConfirm(true)}
              disabled={!qty || parseInt(qty) < 1}
              style={{
                width:"100%", padding:"12px", fontSize:13, fontWeight:700,
                cursor:"pointer", fontFamily:"var(--font)", border:"none",
                background: side==="BUY" ? "var(--green)" : "var(--red)",
                color: "#000",
                opacity: !qty || parseInt(qty) < 1 ? 0.5 : 1,
              }}>
              {side} {qty || 0} × {symbol}
            </button>
          ) : (
            <div>
              <div style={{
                padding:"10px 12px", marginBottom:10, fontSize:12,
                background:"rgba(255,208,96,0.1)",
                border:"1px solid rgba(255,208,96,0.3)",
                color:"var(--yellow)", textAlign:"center",
              }}>
                ⚠ Confirm {side} {qty} shares of {symbol}
                {orderType==="LIMIT" ? ` @ ₹${price}` : " at MARKET price"}?
              </div>
              <div style={{display:"flex", gap:8}}>
                <button
                  className={`auth-btn${orderMutation.isPending?" loading":""}`}
                  onClick={() => orderMutation.mutate()}
                  disabled={orderMutation.isPending}
                  style={{
                    flex:1,
                    background: side==="BUY" ? "var(--green)" : "var(--red)",
                    color:"#000", border:"none",
                  }}>
                  {orderMutation.isPending ? "PLACING..." : `CONFIRM ${side}`}
                </button>
                <button onClick={() => setConfirm(false)} style={{
                  padding:"12px 16px", cursor:"pointer", fontFamily:"var(--font)",
                  background:"transparent", border:"1px solid var(--border)",
                  color:"var(--muted)", fontSize:12,
                }}>CANCEL</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}