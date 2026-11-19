/**
 * Trade Terminal
 * ==============
 * Unified terminal merging Live Market data + Trade execution
 * Modelled exactly after the Excel Trade Terminal layout:
 *   Row 1: Account summary (Cash, Margin, Overall PnL, Order Type, Trade Mode)
 *   Row 3+: Per-symbol rows with OHLC, VWAP, Best Buy/Sell, LTP, signals, entry/exit, T/SL, PnL
 */
import { memo, useState, useEffect, useRef, useMemo, useCallback, Fragment } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import { wsBase } from "@/utils/ws";
import { useAuthStore } from "@/store/auth";
import { notifyOrder, notifyError } from "@/store/notifications";
import toast from "react-hot-toast";
import { Link } from "react-router-dom";

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
  "SENSEX":     {security_id:"51",    segment:"IDX_I"},
  "BANKEX":     {security_id:"83",    segment:"IDX_I"},
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

const T_HEADERS: Record<string, string> = {
  "T11.8": "T1", "T23.8": "T2", "T38.2": "T3", "T50": "T4", "T61.8": "T5",
  "T78.6": "T6", "T100": "T7", "T1.618": "T8", "T2.618": "T9",
  "p_high": "PREV HIGH", "p_low": "PREV LOW",
  "P_HIGH": "PREV HIGH", "P_LOW": "PREV LOW",
  "P.HIGH": "PREV HIGH", "P.LOW": "PREV LOW",
};

function isOptionScript(symbol: string, segment?: string): boolean {
  const seg = (segment || "").toUpperCase().trim();
  if (["NSE_FNO", "NFO", "BSE_FNO", "BFO", "MCX", "OPTIDX", "OPTSTK", "FUTIDX", "FUTSTK"].includes(seg)) {
    return true;
  }
  if (["NSE_EQ", "BSE_EQ", "EQ"].includes(seg)) {
    return false;
  }
  const sym = (symbol || "").toUpperCase().trim();
  if (/\b(CALL|PUT|CE|PE|FUT|OPT)\b/.test(sym) || /\d+\s*(CE|PE|CALL|PUT)\b/.test(sym)) {
    return true;
  }
  return false;
}

function columnTitle(name: string) {
  return T_HEADERS[name] ?? name;
}

export default function TerminalPage() {
  const qc = useQueryClient();
  const { accessToken, user } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const [liveData,   setLiveData]   = useState<Record<string, any>>({});
  const [wsStatus,   setWsStatus]   = useState<"connecting"|"live"|"polling">("connecting");
  const [showAdd,    setShowAdd]    = useState(false);
  const [formulaRow, setFormulaRow] = useState<{id:string,symbol:string}|null>(null);
  const [showColumns, setShowColumns] = useState(false);
  const [orderPanel,  setOrderPanel]  = useState<{symbol:string,security_id:string,segment:string,prefillSide?:string,prefillPrice?:number}|null>(null);
  const [showImportPositions, setShowImportPositions] = useState(false);
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
    const url    = `${wsBase()}/api/ws/market?token=${accessToken}&symbols=ALL`;

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
      const data = await api.get("/market/live-quotes", { params: { symbols: watchlist.join(",") } }).then(r => r.data);
      if (wsStatus !== "live") {
        const map: Record<string,any> = {};
        data.forEach((q: any) => { map[q.symbol] = q; });
        setLiveData(map);
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
  const [viewMode, setViewMode] = useState<"equity" | "options" | "mcx" | "algo">("equity");

  const visibleCols = useMemo(() => {
    return (allCols ?? [])
      .filter((c: any) => {
        const k = (c.col_key || c.name || "").toLowerCase().trim();
        return c.is_visible && k !== "p_close" && k !== "p.close" && k !== "prev close";
      })
      .sort((a: any, b: any) => a.col_order - b.col_order);
  }, [allCols]);

  const colsFor = useCallback((book: string) => {
    const forBook = visibleCols.filter((c: any) => {
      const colBook = (c.book || "equity").toLowerCase();
      if (!c.formula) return true; // default columns (open, high, ltp, etc.) are shared
      return colBook === book || colBook === "shared" || (book === "mcx" && colBook === "equity");
    });

    // Strictly deduplicate by col_key or name to prevent duplicate columns in table
    const seen = new Set<string>();
    return forBook.filter((c: any) => {
      const key = (c.col_key || c.name || "").toLowerCase().trim();
      if (!key || key === "symbol" || key === "p_close" || key === "p.close" || key === "prev close" || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [visibleCols]);

  const customCols = useMemo(() => {
    return (allCols ?? []).filter((c: any) => c.col_type === "custom" && c.is_visible);
  }, [allCols]);

  const isMcxSymbol = useCallback((sym: string) => {
    const inst = instrMap[sym] as any;
    const exch = inst?.exchange || (inst?.segment === "MCX_COMM" ? "MCX" : "");
    if (exch === "MCX" || inst?.segment === "MCX_COMM") return true;
    const s = sym.toUpperCase();
    return s.startsWith("GOLD") || s.startsWith("SILVER") || s.startsWith("CRUDEOIL") ||
           s.startsWith("NATURALGAS") || s.startsWith("COPPER") || s.startsWith("ZINC") ||
           s.startsWith("NICKEL") || s.startsWith("ALUMINIUM") || s.startsWith("LEAD");
  }, [instrMap]);

  const isOptionSymbol = useCallback((sym: string) => {
    if (isMcxSymbol(sym)) return false;
    const inst = instrMap[sym];
    const seg = inst?.segment || (SECURITY_IDS as Record<string, {segment: string}>)[sym]?.segment;
    if (seg === "NSE_FNO" || seg === "BSE_FNO") return true;
    return /\s\d{2,}\s(CE|PE|CALL|PUT)$/i.test(sym) || /-(CE|PE)$/i.test(sym);
  }, [isMcxSymbol, instrMap]);

  const mcxSymbols = useMemo(() => watchlist.filter(isMcxSymbol), [watchlist, isMcxSymbol]);
  const optionSymbols = useMemo(() => watchlist.filter((sym) => !isMcxSymbol(sym) && isOptionSymbol(sym)), [watchlist, isMcxSymbol, isOptionSymbol]);
  const equitySymbols = useMemo(() => watchlist.filter((sym) => !isMcxSymbol(sym) && !isOptionSymbol(sym)), [watchlist, isMcxSymbol, isOptionSymbol]);

  const ticksRef = useRef<Record<string, any>>({});
  ticksRef.current = liveData;
  const booksRef = useRef({ equity: equitySymbols, options: optionSymbols, mcx: mcxSymbols });
  booksRef.current = { equity: equitySymbols, options: optionSymbols, mcx: mcxSymbols };

  function ticksFor(symbols: string[]) {
    return symbols.map((sym) => {
      const q = ticksRef.current[sym] ?? {};
      return {
        symbol: sym,
        ltp: q.ltp ?? null,
        open: q.open ?? null,
        high: q.high ?? null,
        low: q.low ?? null,
        close: q.close ?? null,
        p_close: q.p_close ?? q.close ?? null,
        p_high: q.p_high ?? q.high ?? null,
        p_low: q.p_low ?? q.low ?? null,
        volume: q.volume ?? null,
        oi: q.oi ?? null,
        vwap: q.vwap ?? q.atp ?? null,
      };
    });
  }

  const { data: columnValues } = useQuery({
    queryKey: ["column-values", equitySymbols.join("|"), optionSymbols.join("|"), mcxSymbols.join("|")],
    queryFn: async () => {
      const load = (symbols: string[], book: string) =>
        symbols.length
          ? api.post("/terminal/column-values", { ticks: ticksFor(symbols), book }).then(r => r.data.values as Record<string, Record<string, any>>)
          : Promise.resolve({});
      const [equity, options, mcx] = await Promise.all([
        load(booksRef.current.equity, "equity"),
        load(booksRef.current.options, "option"),
        load(booksRef.current.mcx, "mcx"),
      ]);
      return { ...equity, ...options, ...mcx };
    },
    enabled: watchlist.length > 0,
    refetchInterval: 1000,
    placeholderData: (prev) => prev,
  });

  const hideColMutation = useMutation({
    mutationFn: ({id, visible}: any) =>
      api.patch(`/terminal/columns/${id}/visibility`, {is_visible: visible}),
    onSuccess: () => refetchCols(),
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
    onSuccess: (res: any) => {
      toast.success("Exit order sent");
      notifyOrder("SELL", res.data?.symbol || "POSITION", res.data?.quantity || 1, res.data?.price);
      qc.invalidateQueries({queryKey:["terminal-rows"]});
    },
    onError: () => {
      toast.error("No active position");
      notifyError("EXIT ORDER FAILED", "No active position or exit order rejected");
    },
  });

  // ── Algo Trading Window Queries & Mutations ──────────────────────────────
  const { data: brokerAccounts } = useQuery({
    queryKey: ["broker-accounts"],
    queryFn: () => api.get("/brokers").then(r => r.data).catch(() => []),
    staleTime: 30_000,
  });
  const activeBroker = (brokerAccounts || []).find((b: any) => b.is_active);
  const isPaperMode = !activeBroker || Boolean(activeBroker.paper_trading);

  const { data: algoRows } = useQuery({
    queryKey: ["algo-rows"],
    queryFn: () => api.get("/terminal/algo-rows").then(r => r.data as any[]),
    refetchInterval: 2000,
  });

  const { data: copySummary } = useQuery({
    queryKey: ["copy-trading-summary"],
    queryFn: () => api.get("/copy-trading/accounts").then(r => r.data),
    refetchInterval: 8000,
  });

  const addAlgoRowMutation = useMutation({
    mutationFn: (payload: string | { symbol: string; segment?: string; exchange?: string; token?: string }) => {
      const body = typeof payload === "string" ? { symbol: payload } : payload;
      return api.post("/terminal/algo-rows", body);
    },
    onSuccess: (res: any) => {
      toast.success(`Added ${res.data?.symbol || "symbol"} to Algo Window`);
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
    onError: () => toast.error("Failed to add to Algo Window"),
  });

  const toggleAlgoMutation = useMutation({
    mutationFn: ({ id, is_algo_active }: { id: string; is_algo_active: boolean }) =>
      api.patch(`/terminal/algo-rows/${id}`, { is_algo_active }),
    onSuccess: (res: any) => {
      const active = res.data?.is_algo_active;
      toast.success(active ? "Automated Trading: ON" : "Manual Mode: ON (Algo OFF)");
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
    onError: () => toast.error("Failed to update Algo state"),
  });

  const updateAlgoRowMutation = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: any }) =>
      api.patch(`/terminal/algo-rows/${id}`, updates),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["algo-rows"] }),
  });

  const deleteAlgoRowMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/terminal/algo-rows/${id}`),
    onSuccess: () => {
      toast.success("Script removed from Algo Window");
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
  });

  const resetAlgoRowMutation = useMutation({
    mutationFn: (id: string) => api.post(`/terminal/algo-rows/${id}/reset`),
    onSuccess: () => {
      toast.success("Trade cycle reset");
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
  });

  const manualAlgoOrderMutation = useMutation({
    mutationFn: ({ id, side }: { id: string; side: "BUY" | "SELL" }) =>
      api.post(`/terminal/algo-rows/${id}/manual-order`, { side }),
    onSuccess: (res: any) => {
      const row = (algoRows ?? []).find((r: any) => r.id === res.data?.row_id);
      const sym = row?.symbol || res.data?.symbol || "ALGO";
      toast.success(`Manual ${res.data?.side} executed @ ₹${res.data?.fill_price}`);
      notifyOrder(res.data?.side || "BUY", sym, res.data?.fill_qty || row?.quantity || 1, res.data?.fill_price);
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || "Manual order execution failed";
      toast.error(msg);
      notifyError("MANUAL ORDER FAILED", msg);
    },
  });

  const killAlgoMutation = useMutation({
    mutationFn: (id: string) => api.post(`/terminal/algo-rows/${id}/kill`),
    onSuccess: () => {
      toast.success("Kill switch activated — trade closed & algo stopped");
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || "Failed to activate kill switch"),
  });

  const importPositionMutation = useMutation({
    mutationFn: (payload: {
      symbol: string;
      quantity: number;
      buy_price: number;
      exchange?: string;
      segment?: string;
      security_id?: string;
      target_type?: string;
      custom_target?: number;
    }) => api.post("/terminal/algo-rows/import-position", payload),
    onSuccess: (res: any) => {
      toast.success(res.data?.message || "Position imported to Algo Window");
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to import position");
    },
  });

  const applyBatchMutation = useMutation({
    mutationFn: ({ batch, book }: { batch: string; book: string }) =>
      api.post("/terminal/columns/apply-batch", { batch, book }),
    onSuccess: (res: any) => {
      const bookLabel = res.data?.book === "algo" ? "Algo Window" : res.data?.books?.join(", ") || "watchlist";
      toast.success(`Applied ${res.data?.applied_batch || "formula"} batch to ${bookLabel}`);
      qc.invalidateQueries({ queryKey: ["terminal-columns"] });
      qc.invalidateQueries({ queryKey: ["column-values"] });
      qc.invalidateQueries({ queryKey: ["batch-presets"] });
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
    },
    onError: () => toast.error("Failed to apply formula batch"),
  });


  const isLive = wsStatus === "live";
  const screenRows = (termRows ?? []).filter((r: any) => watchlist.includes(r.symbol));

  // Build unified row list — watchlist symbols merged with terminal rows
  const termRowMap: Record<string, any> = {};
  (termRows ?? []).forEach((r: any) => { termRowMap[r.symbol] = r; });

  const overallPnl = (termRows ?? []).reduce((s: number, r: any) => s + (r.pnl ?? 0), 0);

  return (
    <Layout>
      {/* ── Unified Terminal Control Strip (Single Line: Watchlist Selector + Account Vitals) ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 10,
          padding: "5px 12px",
          marginBottom: 8,
          borderRadius: 4,
          border: "1px solid var(--border)",
          background: "var(--surface)",
        }}
      >
        {/* Left: Tab Switcher (EQUITY | OPTIONS | MCX | ALGO WINDOW) */}
        <div style={{ display: "inline-flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
          <div className="tab-switcher" style={{ margin: 0, padding: 2 }}>
            <button
              type="button"
              className={`tab-btn ${viewMode === "equity" ? "active" : ""}`}
              onClick={() => setViewMode("equity")}
              style={{ padding: "4px 10px", fontSize: 11 }}
            >
              EQUITY ({equitySymbols.length})
            </button>
            <button
              type="button"
              className={`tab-btn ${viewMode === "options" ? "active" : ""}`}
              onClick={() => setViewMode("options")}
              style={{ padding: "4px 10px", fontSize: 11 }}
            >
              OPTIONS ({optionSymbols.length})
            </button>
            <button
              type="button"
              className={`tab-btn ${viewMode === "mcx" ? "active" : ""}`}
              onClick={() => setViewMode("mcx")}
              style={{ padding: "4px 10px", fontSize: 11 }}
            >
              MCX ({mcxSymbols.length})
            </button>
            <button
              type="button"
              className={`tab-btn ${viewMode === "algo" ? "active" : ""}`}
              onClick={() => setViewMode("algo")}
              style={{ padding: "4px 10px", fontSize: 11 }}
            >
              ALGO WINDOW ({algoRows?.length ?? 0})
            </button>
          </div>
        </div>

        {/* Right: AVAIL BALANCE | USED MARGIN | P&L | ACTIVE | IN POSITION | COLUMNS | ADD SYMBOL */}
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginLeft: "auto" }}>
          {/* AVAIL BALANCE */}
          <div style={{ display: "inline-flex", alignItems: "baseline", gap: 4 }}>
            <span style={{ fontSize: 9, letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>
              AVAIL BALANCE
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)", fontFamily: "monospace" }}>
              {funds?.availabelBalance != null ? `₹${Number(funds.availabelBalance).toLocaleString()}` : "—"}
            </span>
          </div>

          <span style={{ color: "var(--border)", fontSize: 11 }}>|</span>

          {/* USED MARGIN */}
          <div style={{ display: "inline-flex", alignItems: "baseline", gap: 4 }}>
            <span style={{ fontSize: 9, letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>
              USED MARGIN
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)", fontFamily: "monospace" }}>
              {funds?.utilizedAmount != null ? `₹${Number(funds.utilizedAmount).toLocaleString()}` : "—"}
            </span>
          </div>

          <span style={{ color: "var(--border)", fontSize: 11 }}>|</span>

          {/* P&L */}
          <div style={{ display: "inline-flex", alignItems: "baseline", gap: 4 }}>
            <span style={{ fontSize: 9, letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>
              P&L
            </span>
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: overallPnl >= 0 ? "var(--green)" : "var(--red)",
                fontFamily: "monospace",
              }}
            >
              {`${overallPnl >= 0 ? "+" : ""}₹${overallPnl.toLocaleString()}`}
            </span>
          </div>

          <span style={{ color: "var(--border)", fontSize: 11 }}>|</span>

          {/* ACTIVE */}
          <div style={{ display: "inline-flex", alignItems: "baseline", gap: 4 }}>
            <span style={{ fontSize: 9, letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>
              ACTIVE
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
              {screenRows.filter((r: any) => r.is_active).length}
            </span>
          </div>

          <span style={{ color: "var(--border)", fontSize: 11 }}>|</span>

          {/* IN POSITION */}
          <div style={{ display: "inline-flex", alignItems: "baseline", gap: 4 }}>
            <span style={{ fontSize: 9, letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>
              IN POSITION
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
              {screenRows.filter((r: any) => r.status === "active").length}
            </span>
          </div>

          {copySummary?.active_copy_count > 0 && (
            <Link
              to="/copy-trading"
              style={{
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 6px",
                fontSize: 10,
                fontWeight: 700,
                color: "var(--green)",
                background: "rgba(0, 230, 118, 0.1)",
                border: "1px solid rgba(0, 230, 118, 0.4)",
                borderRadius: 3,
                letterSpacing: 0.5,
              }}
              title="Click to open Dhan Copy Trading Hub"
            >
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--green)" }} />
              COPY: {copySummary.active_copy_count}
            </Link>
          )}

          {/* COLUMNS */}
          <button
            type="button"
            className="exit-btn"
            style={{
              fontSize: 10,
              padding: "3px 8px",
              color: "var(--yellow)",
              borderColor: "rgba(255,183,3,0.3)",
              lineHeight: 1.2,
              fontWeight: 700,
            }}
            onClick={() => setShowColumns(true)}
          >
            COLUMNS
          </button>

          {/* ADD SYMBOL */}
          <button
            type="button"
            className="connect-btn"
            style={{
              fontSize: 10,
              padding: "3px 10px",
              lineHeight: 1.2,
              fontWeight: 700,
            }}
            onClick={() => setShowAdd((v) => !v)}
          >
            {showAdd ? "CANCEL" : "+ ADD SYMBOL"}
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
      {showColumns && (
        <AdminColumnManager isAdmin={isAdmin} onClose={() => setShowColumns(false)} />
      )}

      {/* ── Import Dhan Positions Modal ──────────────────────────────────── */}
      {showImportPositions && (
        <ImportDhanPositionsModal
          isOpen={showImportPositions}
          onClose={() => setShowImportPositions(false)}
          onImport={(payload) => importPositionMutation.mutateAsync(payload)}
          existingSymbols={(algoRows ?? []).map((r: any) => r.symbol)}
        />
      )}

      {orderPanel && (
        <OrderPanel
          symbol={orderPanel.symbol}
          securityId={orderPanel.security_id}
          segment={orderPanel.segment}
          ltp={liveData[orderPanel.symbol]?.ltp ?? null}
          onClose={() => setOrderPanel(null)}
          prefillSide={orderPanel.prefillSide}
          prefillPrice={orderPanel.prefillPrice}
        />
      )}

      {/* ── Add Symbol Panel ────────────────────────────────────────────────── */}
      {showAdd && (
        <AddSymbolPanel
          onAdded={() => {
            qc.invalidateQueries({queryKey:["watchlist"]});
            setShowAdd(false);
          }}
          onAddToAlgo={(inst) => {
            addAlgoRowMutation.mutate({
              symbol: inst.symbol,
              segment: inst.exchange_segment || inst.segment || "NSE_EQ",
              exchange: inst.exchange || "NSE",
              token: inst.security_id,
            });
            setShowAdd(false);
          }}
        />
      )}

      {/* ── Separate List Views (EQUITY | OPTIONS | MCX | ALGO WINDOW) ──────── */}
      {viewMode === "equity" && (
        equitySymbols.length === 0 ? (
          <div style={{
            padding:"40px 20px", textAlign:"center", color:"var(--muted)",
            fontSize:12, border:"1px solid var(--border)", background:"var(--surface)"
          }}>
            No equity symbols in watchlist. Click <strong style={{color:"var(--green)"}}>+ ADD SYMBOL</strong> to add.
          </div>
        ) : (
          <TerminalTable
            title="EQUITY"
            book="equity"
            onOrder={(sym, inst, prefillSide, prefillPrice) => setOrderPanel({symbol:sym, ...inst, prefillSide, prefillPrice: prefillPrice ?? undefined})}
            onAddToAlgo={(sym, seg, exch, tok) => addAlgoRowMutation.mutate({ symbol: sym, segment: seg || instrMap[sym]?.segment || "NSE_EQ", exchange: exch || "NSE", token: tok })}
            instrMap={instrMap}
            watchlist={equitySymbols}
            liveData={liveData}
            termRowMap={termRowMap}
            visibleCols={colsFor("equity")}
            columnValues={columnValues ?? {}}
            isAdmin={isAdmin}
            onRemoveSymbol={(sym)=>removeMutation.mutate(sym)}
            onExitRow={(id)=>exitRowMutation.mutate(id)}
            onFormulaRow={(id,sym)=>setFormulaRow({id,symbol:sym})}
          />
        )
      )}

      {viewMode === "options" && (
        optionSymbols.length === 0 ? (
          <div style={{
            padding:"40px 20px", textAlign:"center", color:"var(--muted)",
            fontSize:12, border:"1px solid var(--border)", background:"var(--surface)"
          }}>
            No option contracts in watchlist. Click <strong style={{color:"var(--green)"}}>+ ADD SYMBOL</strong> to search & add options.
          </div>
        ) : (
          <TerminalTable
            title="OPTIONS"
            book="option"
            onOrder={(sym, inst, prefillSide, prefillPrice) => setOrderPanel({symbol:sym, ...inst, prefillSide, prefillPrice: prefillPrice ?? undefined})}
            onAddToAlgo={(sym, seg, exch, tok) => addAlgoRowMutation.mutate({ symbol: sym, segment: seg || instrMap[sym]?.segment || "NSE_FNO", exchange: exch || "NFO", token: tok })}
            instrMap={instrMap}
            watchlist={optionSymbols}
            liveData={liveData}
            termRowMap={termRowMap}
            visibleCols={colsFor("option")}
            columnValues={columnValues ?? {}}
            isAdmin={isAdmin}
            onRemoveSymbol={(sym)=>removeMutation.mutate(sym)}
            onExitRow={(id)=>exitRowMutation.mutate(id)}
            onFormulaRow={(id,sym)=>setFormulaRow({id,symbol:sym})}
          />
        )
      )}

      {viewMode === "mcx" && (
        mcxSymbols.length === 0 ? (
          <div style={{
            padding:"40px 20px", textAlign:"center", color:"var(--muted)",
            fontSize:12, border:"1px solid var(--border)", background:"var(--surface)"
          }}>
            No MCX commodity contracts in watchlist. Click <strong style={{color:"var(--green)"}}>+ ADD SYMBOL</strong> to search & add GOLD, SILVER, CRUDEOIL, etc.
          </div>
        ) : (
          <TerminalTable
            title="MCX COMMODITIES"
            book="mcx"
            onOrder={(sym, inst, prefillSide, prefillPrice) => setOrderPanel({symbol:sym, ...inst, prefillSide, prefillPrice: prefillPrice ?? undefined})}
            onAddToAlgo={(sym, seg, exch, tok) => addAlgoRowMutation.mutate({ symbol: sym, segment: seg || instrMap[sym]?.segment || "MCX_COMM", exchange: exch || "MCX", token: tok })}
            instrMap={instrMap}
            watchlist={mcxSymbols}
            liveData={liveData}
            termRowMap={termRowMap}
            visibleCols={colsFor("mcx")}
            columnValues={columnValues ?? {}}
            isAdmin={isAdmin}
            onRemoveSymbol={(sym)=>removeMutation.mutate(sym)}
            onExitRow={(id)=>exitRowMutation.mutate(id)}
            onFormulaRow={(id,sym)=>setFormulaRow({id,symbol:sym})}
          />
        )
      )}

      {/* ── Algo Trading Window Table ────────────────────────────────────── */}
      {viewMode === "algo" && (
        <AlgoWindowTable
          algoRows={algoRows ?? []}
          isPaper={isPaperMode}
          onToggleAlgo={(id, currentActive) => toggleAlgoMutation.mutate({ id, is_algo_active: !currentActive })}
          onUpdateRow={(id, updates) => updateAlgoRowMutation.mutate({ id, updates })}
          onDeleteRow={(id) => deleteAlgoRowMutation.mutate(id)}
          onResetRow={(id) => resetAlgoRowMutation.mutate(id)}
          onManualOrder={(id, side) => manualAlgoOrderMutation.mutate({ id, side })}
          onKillRow={(id) => killAlgoMutation.mutate(id)}
          onOpenImportPositions={() => setShowImportPositions(true)}
        />
      )}

    </Layout>
  );
}

// ── Add Symbol Panel ──────────────────────────────────────────────────────────
function AddSymbolPanel({ onAdded, onAddToAlgo }: {
  onAdded: () => void;
  onAddToAlgo?: (inst: any) => void;
}) {
  const [query,   setQuery]   = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const addMutation = useMutation({
    mutationFn: (inst: any) => api.post("/market/watchlist", {
      symbol:           inst.symbol,
      security_id:      inst.security_id,
      exchange_segment: inst.exchange_segment || inst.segment || "NSE_EQ",
    }),
    onSuccess: (_, inst) => { toast.success(`${inst.symbol} added to watchlist`); onAdded(); },
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
    <div className="card" style={{marginBottom:8}}>
      <div style={{padding:"8px 12px"}}>
        <div style={{position:"relative", maxWidth:500, display:"flex", gap:8}}>
          <input className="field-input" value={query}
            onChange={e => setQuery(e.target.value)} autoFocus
            placeholder="Search symbol or option... e.g. TCS, BANKNIFTY 61000 CE, GOLD"
            style={{flex:1}} />
          {loading && <span style={{position:"absolute", right:12, top:"50%",
            transform:"translateY(-50%)", color:"var(--muted)", fontSize:11}}>...</span>}
        </div>
        {results.length > 0 && (
          <div style={{marginTop:6, border:"1px solid var(--border)",
            background:"var(--surface)", maxHeight:240, overflowY:"auto", maxWidth:680}}>
            {results.map(inst => (
              <div key={`${inst.exchange_segment}-${inst.security_id}`}
                style={{padding:"8px 12px", display:"flex", justifyContent:"space-between",
                  alignItems:"center", borderBottom:"1px solid var(--border)", cursor:"pointer"}}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--green-dim)")}
                onMouseLeave={e => (e.currentTarget.style.background = "")}>
                <div>
                  <span style={{fontWeight:700, color:"var(--green)", fontSize:12}}>{inst.symbol}</span>
                  <span style={{fontSize:10, color:"var(--muted)", marginLeft:8}}>{inst.name}</span>
                </div>
                <div style={{display:"flex", gap:6, alignItems:"center"}}>
                  <span style={{fontSize:9, color:"var(--muted)"}}>{inst.exchange} · {inst.series || inst.exchange_segment}</span>
                  <button className="connect-btn" style={{padding:"3px 8px", fontSize:10}}
                    onClick={() => addMutation.mutate(inst)}
                    disabled={addMutation.isPending}
                    title="Add to Watchlist"
                  >
                    + WATCHLIST
                  </button>
                  {onAddToAlgo && (
                    <button
                      type="button"
                      className="connect-btn"
                      style={{
                        padding: "3px 8px",
                        fontSize: 10,
                        background: "rgba(0, 180, 216, 0.15)",
                        borderColor: "rgba(0, 180, 216, 0.45)",
                        color: "#08b6de",
                      }}
                      onClick={() => onAddToAlgo(inst)}
                      title="Add directly to Algo Window"
                    >
                      + ALGO
                    </button>
                  )}
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
      target_formula: d.target_formula ?? "",
      sl_formula:     d.sl_formula     ?? "",
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
      target_formula: form.target_formula || null,
      sl_formula:     form.sl_formula     || null,
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
              ƒ FORMULA CONFIG
            </div>
            <div style={{fontSize:11, color:"var(--muted)"}}>
              {symbol} — Admin only · Hidden from users
            </div>
          </div>
          <button onClick={onClose}
            style={{background:"transparent",border:"none",color:"var(--muted)",
              cursor:"pointer",fontSize:18}}>×</button>
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
              <label className="field-label">TARGET PRICE</label>
              <input className="field-input" value={form.target_formula}
                onChange={set("target_formula")} placeholder="entry * 1.02" />
            </div>
            <div className="field">
              <label className="field-label">STOP PRICE</label>
              <input className="field-input" value={form.sl_formula}
                onChange={set("sl_formula")} placeholder="entry * 0.99" />
            </div>
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
export function AdminColumnManager({ isAdmin = false, onClose }: { isAdmin?: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const emptyForm = (book: "equity" | "option") => ({
    name: "", formula: "", col_order: 0, width: 80, color_rules: "", book,
  });
  const [form, setForm] = useState(emptyForm("equity"));
  const [editId,    setEditId]    = useState<string|null>(null);
  const [validMsg,  setValidMsg]  = useState("");
  const [validOk,   setValidOk]   = useState<boolean|null>(null);
  const set = (k: string) => (e: any) => setForm(f => ({...f, [k]: e.target.value}));

  const { data: columns } = useQuery({
    queryKey: ["terminal-columns"],
    queryFn: () => api.get("/terminal/columns").then(r => r.data),
  });
  const defaultCols = useMemo(() => {
    const raw = (columns ?? []).filter((col: any) => !col.formula || col.col_type === "default");
    const seen = new Set<string>();
    return raw.filter((col: any) => {
      const k = (col.col_key || col.name || "").toLowerCase().trim();
      if (!k || k === "p_close" || k === "p.close" || k === "prev close" || seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  }, [columns]);

  const listed = useMemo(() => {
    const raw = (columns ?? []).filter((col: any) => col.formula && (col.book || "equity") === form.book);
    const seen = new Set<string>();
    return raw.filter((col: any) => {
      const k = (col.name || "").toLowerCase().trim();
      if (!k || seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  }, [columns, form.book]);

  const toggleVisibilityMutation = useMutation({
    mutationFn: ({ id, is_visible }: { id: string; is_visible: boolean }) =>
      api.patch(`/terminal/columns/${id}/visibility`, { is_visible }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["terminal-columns"] });
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed to toggle visibility"),
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
        book:        form.book,
      };
      return editId
        ? api.put(`/terminal/columns/${editId}`, payload)
        : api.post("/terminal/columns", payload);
    },
    onSuccess: () => {
      toast.success(editId ? "Column updated" : "Column added");
      qc.invalidateQueries({queryKey:["terminal-columns"]});
      qc.invalidateQueries({queryKey:["column-values"]});
      setForm(f => emptyForm(f.book));
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
      book: col.book === "option" ? "option" : "equity",
    });
    setValidMsg(""); setValidOk(null);
  }

  const { data: presets } = useQuery({
    queryKey: ["column-presets", form.book],
    queryFn: () => api.get("/terminal/column-presets", { params: { book: form.book } }).then(r => r.data as {name:string,formula:string,colors:string}[]),
  });

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
              ƒ FORMULA COLUMNS
            </div>
            <div style={{fontSize:11, color:"var(--muted)"}}>
              Equity and options each keep their own formulas. Price columns stay on both tables.
            </div>
          </div>
          <button onClick={onClose}
            style={{background:"transparent",border:"none",
              color:"var(--muted)",cursor:"pointer",fontSize:18}}>×</button>
        </div>

        <div style={{padding:"20px"}}>
          {/* Formula Batch Selection */}
          <div style={{
            marginBottom: 20, padding: "14px 16px",
            border: "1px solid rgba(0, 230, 118, 0.3)", background: "rgba(0, 230, 118, 0.04)",
            borderRadius: 4
          }}>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10}}>
              <div>
                <div style={{fontSize:11, fontWeight:700, color:"var(--green)", letterSpacing:1}}>
                  FORMULA BATCH PRESETS
                </div>
                <div style={{fontSize:10, color:"var(--muted)", marginTop:2}}>
                  Apply pre-configured formula batches in sequence
                </div>
              </div>
            </div>
            <div style={{display:"flex", gap:10, flexWrap:"wrap"}}>
              <button
                type="button"
                onClick={() => {
                  if (confirm("Apply Fibonacci Formula batch? This configures default columns and Fibonacci target columns.")) {
                    api.post("/terminal/columns/apply-batch", { batch: "Fibonacci Formula", book: "both" })
                      .then(() => { toast.success("Applied Fibonacci Formula batch"); qc.invalidateQueries({queryKey:["terminal-columns"]}); })
                      .catch(() => toast.error("Failed to apply batch"));
                  }
                }}
                style={{
                  padding:"8px 16px", fontSize:11, cursor:"pointer",
                  fontFamily:"var(--font)", fontWeight:700, letterSpacing:0.5,
                  background:"rgba(0, 230, 118, 0.15)", border:"1px solid var(--green)",
                  color:"var(--green)", borderRadius:3,
                }}
              >
                APPLY FIBONACCI BATCH
              </button>
            </div>
          </div>

          {/* Default columns toggle section */}
          <div style={{
            marginBottom: 20, padding: "14px 16px",
            border: "1px solid var(--border)", background: "rgba(0,0,0,0.2)",
            borderRadius: 4
          }}>
            <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10}}>
              <div>
                <div style={{fontSize:11, fontWeight:700, color:"var(--green)", letterSpacing:1}}>
                  DEFAULT COLUMNS (PRICE & MARKET DATA)
                </div>
                <div style={{fontSize:10, color:"var(--muted)", marginTop:2}}>
                  Click any column badge to toggle visibility in the terminal table
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (confirm("Reset columns to defaults?")) {
                    api.post("/terminal/columns/reset")
                      .then(() => { toast.success("Reset"); qc.invalidateQueries({queryKey:["terminal-columns"]}); })
                      .catch(() => toast.error("Failed"));
                  }
                }}
                style={{
                  padding:"4px 10px", fontSize:10, cursor:"pointer",
                  background:"transparent", border:"1px solid var(--border)",
                  color:"var(--muted)", fontFamily:"var(--font)"
                }}>
                ↺ RESET ALL
              </button>
            </div>
            <div style={{display:"flex", flexWrap:"wrap", gap:8}}>
              {defaultCols.map((col: any) => {
                const isVis = col.is_visible !== false;
                return (
                  <button
                    key={col.id || col.col_key || col.name}
                    type="button"
                    onClick={() => toggleVisibilityMutation.mutate({ id: col.id || col.col_key, is_visible: !isVis })}
                    style={{
                      display:"inline-flex", alignItems:"center", gap:6,
                      padding:"6px 12px", fontSize:11, cursor:"pointer",
                      fontFamily:"var(--font)", fontWeight:600,
                      background: isVis ? "rgba(47, 158, 143, 0.16)" : "rgba(255,255,255,0.03)",
                      border: `1px solid ${isVis ? "var(--green)" : "var(--border)"}`,
                      color: isVis ? "var(--green)" : "var(--muted)",
                      borderRadius: 3, transition: "all 0.15s",
                    }}
                    title={isVis ? `Click to hide ${col.name}` : `Click to show ${col.name}`}
                  >
                    <span>{isVis ? "●" : "○"}</span>
                    <span>{columnTitle(col.name)}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{display:"flex", gap:8, marginBottom:16}}>
            {(["equity", "option"] as const).map((book) => (
              <button key={book} type="button"
                onClick={() => { setForm(emptyForm(book)); setEditId(null); setValidMsg(""); setValidOk(null); }}
                style={{
                  padding:"6px 14px", fontSize:11, cursor:"pointer", fontFamily:"var(--font)", fontWeight:700,
                  background: form.book === book ? "rgba(0,255,136,0.12)" : "transparent",
                  border: `1px solid ${form.book === book ? "rgba(0,255,136,0.5)" : "var(--border)"}`,
                  color: form.book === book ? "var(--green)" : "var(--muted)",
                }}>
                {book === "equity" ? "EQUITY" : "OPTIONS"}
              </button>
            ))}
          </div>
          {/* Example templates */}
          <div style={{marginBottom:16}}>
            <div style={{fontSize:10,letterSpacing:2,color:"var(--muted)",marginBottom:8}}>
              QUICK TEMPLATES (click to load)
            </div>
            <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
              {(presets ?? []).map(ex => (
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
                {validateMutation.isPending ? "..." : "VALIDATE"}
              </button>
              {validMsg && (
                <span style={{
                  fontSize:11,
                  color: validOk ? "var(--green)" : "var(--red)",
                }}>
                  {validOk ? "VALID: " : "ERROR: "}{validMsg}
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
                    setForm({name:"",formula:"",col_order:0,width:80,color_rules:"",book:form.book});
                    setValidMsg(""); setValidOk(null);
                  }}
                  style={{padding:"10px 16px"}}>CANCEL</button>
              )}
            </div>
          </div>

          {/* All columns list with show/hide/delete */}
          {listed.length > 0 && (
            <div>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
                <div style={{fontSize:10,letterSpacing:2,color:"var(--muted)"}}>
                  {form.book === "equity" ? "EQUITY" : "OPTIONS"} FORMULAS — click × to remove, eye to show/hide
                </div>
                <button
                  onClick={() => { if(confirm("Remove equity and options formulas and restore the price columns?")) api.post("/terminal/columns/reset").then(()=>{toast.success("Reset");qc.invalidateQueries({queryKey:["terminal-columns"]});}).catch(()=>toast.error("Failed")); }}
                  style={{padding:"4px 12px",fontSize:10,cursor:"pointer",
                    background:"transparent",border:"1px solid var(--border)",
                    color:"var(--muted)",fontFamily:"var(--font)"}}>
                  ↺ RESET DEFAULTS
                </button>
              </div>
              <div style={{display:"flex",flexWrap:"wrap",gap:6}}>
                {listed.map((col: any) => (
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
                    }}>{columnTitle(col.name)}</span>
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
                      {col.is_visible ? "●" : "○"}
                    </button>
                    <button
                      onClick={() => { if(confirm(`Remove "${col.name}" column?`)) deleteMutation.mutate(col.id); }}
                      title="Remove column"
                      style={{background:"transparent",border:"none",
                        color:"rgba(255,68,102,0.5)",cursor:"pointer",
                        fontSize:10,padding:0}}>×</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {listed.length === 0 && (
            <div style={{color:"var(--muted)",fontSize:12,textAlign:"center",padding:20}}>
              No formulas on this book yet. Load a template above, or add one.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const TARGET_COLS = [
  { key: "T1",  aliasKey: "t1",  altKey: "t11_8", label: "T1",  pctEquity: "0.118%",  pctOption: "11.8%",  color: "var(--green)" },
  { key: "T2",  aliasKey: "t2",  altKey: "t23_8", label: "T2",  pctEquity: "0.238%",  pctOption: "23.8%",  color: "var(--green)" },
  { key: "T3",  aliasKey: "t3",  altKey: "t38_2", label: "T3",  pctEquity: "0.382%",  pctOption: "38.2%",  color: "var(--green)" },
  { key: "T4",  aliasKey: "t4",  altKey: "t50",   label: "T4",  pctEquity: "0.500%",  pctOption: "50.0%",  color: "var(--green)" },
  { key: "T5",  aliasKey: "t5",  altKey: "t61_8", label: "T5",  pctEquity: "0.618%",  pctOption: "61.8%",  color: "var(--green)" },
  { key: "T6",  aliasKey: "t6",  altKey: "t78_6", label: "T6",  pctEquity: "0.786%",  pctOption: "78.6%",  color: "var(--green)" },
  { key: "T7",  aliasKey: "t7",  altKey: "t100",  label: "T7",  pctEquity: "1.000%",  pctOption: "100.0%", color: "var(--green)" },
  { key: "T8",  aliasKey: "t8",  altKey: "t1_618", label: "T8", pctEquity: "1.618%", pctOption: "161.8%", color: "var(--green)" },
  { key: "T9",  aliasKey: "t9",  altKey: "t2_618", label: "T9", pctEquity: "2.618%", pctOption: "261.8%", color: "var(--green)" },
];

function isTargetArmed(targetType: string, tcKey: string): boolean {
  const tt = (targetType || "T1").toUpperCase().trim();
  const k = tcKey.toUpperCase().trim();
  if (tt === k) return true;
  const map: Record<string, string> = {
    "T11.8": "T1", "T11_8": "T1", "TGT1": "T1",
    "T23.8": "T2", "T23_8": "T2", "TGT2": "T2",
    "T38.2": "T3", "T38_2": "T3", "TGT3": "T3",
    "T50": "T4",
    "T61.8": "T5", "T61_8": "T5",
    "T78.6": "T6", "T78_6": "T6",
    "T100": "T7",
    "T1.618": "T8", "T1_618": "T8",
    "T2.618": "T9", "T2_618": "T9",
  };
  return map[tt] === k;
}

function normalizeTargetType(targetType: string): string {
  const tt = (targetType || "T1").toUpperCase().trim();
  if (tt === "CUSTOM" || tt === "KILL") return tt;
  const map: Record<string, string> = {
    "T11.8": "T1", "T11_8": "T1", "TGT1": "T1",
    "T23.8": "T2", "T23_8": "T2", "TGT2": "T2",
    "T38.2": "T3", "T38_2": "T3", "TGT3": "T3",
    "T50": "T4",
    "T61.8": "T5", "T61_8": "T5",
    "T78.6": "T6", "T78_6": "T6",
    "T100": "T7",
    "T1.618": "T8", "T1_618": "T8",
    "T2.618": "T9", "T2_618": "T9",
  };
  return map[tt] || tt;
}

function normalizeEntryType(entryType: string): string {
  const et = (entryType || "FORMULA").toUpperCase().trim();
  if (et === "CUSTOM" || et === "FORMULA") return et;
  const map: Record<string, string> = {
    "T11.8": "T1", "T11_8": "T1", "TGT1": "T1",
    "T23.8": "T2", "T23_8": "T2", "TGT2": "T2",
    "T38.2": "T3", "T38_2": "T3", "TGT3": "T3",
    "T50": "T4",
    "T61.8": "T5", "T61_8": "T5",
    "T78.6": "T6", "T78_6": "T6",
    "T100": "T7",
    "T1.618": "T8", "T1_618": "T8",
    "T2.618": "T9", "T2_618": "T9",
  };
  return map[et] || et;
}

// ── Import Dhan Positions Modal ──────────────────────────────────────────────
function ImportDhanPositionsModal({
  isOpen,
  onClose,
  onImport,
  existingSymbols = [],
}: {
  isOpen: boolean;
  onClose: () => void;
  onImport: (pos: any) => Promise<any> | void;
  existingSymbols?: string[];
}) {
  const [selectedTargets, setSelectedTargets] = useState<Record<string, string>>({});
  const [importingSym, setImportingSym] = useState<string | null>(null);

  const { data, isLoading, isFetching, refetch, error } = useQuery({
    queryKey: ["dhan-positions"],
    queryFn: () => api.get("/terminal/dhan-positions").then((r) => r.data),
    enabled: isOpen,
    staleTime: 5000,
  });

  if (!isOpen) return null;

  const positions: any[] = data?.positions || [];
  const accountName = data?.account_name || "Dhan";
  const isPaper = Boolean(data?.is_paper);

  const handleImport = async (pos: any) => {
    const sym = pos.symbol;
    const targetType = selectedTargets[sym] || "T1";
    setImportingSym(sym);
    try {
      await onImport({
        symbol: pos.symbol,
        quantity: pos.quantity || Math.abs(pos.net_qty),
        buy_price: pos.buy_price || 0,
        segment: pos.segment || "NSE_EQ",
        exchange: pos.exchange || "NSE",
        security_id: pos.security_id || "",
        target_type: targetType,
      });
    } finally {
      setImportingSym(null);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.85)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          width: 840,
          maxWidth: "95vw",
          maxHeight: "90vh",
          overflowY: "auto",
          borderRadius: 4,
          boxShadow: "0 10px 40px rgba(0,0,0,0.7)",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "14px 18px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "rgba(56, 189, 248, 0.05)",
          }}
        >
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8", letterSpacing: 1.2 }}>
              IMPORT DHAN POSITIONS INTO ALGO WINDOW
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              Import live open positions or holdings directly into SELL ONLY mode for automated target exit (T1-T9 / Custom) and Stop Loss.
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--muted)",
              cursor: "pointer",
              fontSize: 18,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        {/* Account Info and Refresh bar */}
        <div
          style={{
            padding: "10px 18px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "var(--surface2)",
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "var(--muted)" }}>Account:</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>{accountName}</span>
            <span className={`badge ${isPaper ? "badge-yellow" : "badge-green"}`} style={{ fontSize: 9, fontWeight: 700 }}>
              {isPaper ? "PAPER TRADING" : "LIVE BROKER"}
            </span>
            <span className="badge badge-gray" style={{ fontSize: 9 }}>
              {positions.length} OPEN POSITIONS
            </span>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            style={{
              padding: "4px 10px",
              fontSize: 10,
              fontWeight: 700,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              color: "var(--text)",
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            {isFetching ? "FETCHING..." : "REFRESH POSITIONS"}
          </button>
        </div>

        {/* Body / Table */}
        <div style={{ padding: "16px 18px" }}>
          {isLoading ? (
            <div style={{ padding: "40px 0", textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
              Fetching live positions from broker...
            </div>
          ) : error ? (
            <div style={{ padding: "30px 0", textAlign: "center", color: "var(--red)", fontSize: 12 }}>
              Failed to load positions from broker. Please ensure broker is connected and active.
            </div>
          ) : positions.length === 0 ? (
            <div style={{ padding: "40px 0", textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
              No open positions found in linked broker account.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--surface2)" }}>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "left" }}>SCRIPT / SYMBOL</th>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "left" }}>SEGMENT</th>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "right" }}>QTY</th>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "right" }}>BUY AVG</th>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "right" }}>LTP</th>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "right" }}>P&L</th>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "center", width: 110 }}>EXIT TARGET</th>
                    <th style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)", textAlign: "center", width: 120 }}>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos: any, idx: number) => {
                    const isAlreadyImported = existingSymbols.includes(pos.symbol);
                    const currentTgt = selectedTargets[pos.symbol] || "T1";
                    const isImporting = importingSym === pos.symbol;

                    return (
                      <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "8px 6px", fontWeight: 700, color: "var(--green)" }}>
                          {pos.symbol}
                        </td>
                        <td style={{ padding: "8px 6px", fontSize: 10, color: "var(--muted)" }}>
                          {pos.segment} ({pos.exchange})
                        </td>
                        <td style={{ padding: "8px 6px", textAlign: "right", fontWeight: 700, color: pos.net_qty > 0 ? "var(--green)" : "var(--red)" }}>
                          {pos.net_qty > 0 ? `+${pos.net_qty}` : pos.net_qty}
                        </td>
                        <td style={{ padding: "8px 6px", textAlign: "right", color: "var(--text)" }}>
                          ₹{Number(pos.buy_price || 0).toLocaleString()}
                        </td>
                        <td style={{ padding: "8px 6px", textAlign: "right", fontWeight: 700, color: "var(--text)" }}>
                          ₹{Number(pos.ltp || 0).toLocaleString()}
                        </td>
                        <td style={{ padding: "8px 6px", textAlign: "right", fontWeight: 700, color: (pos.pnl || 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                          {(pos.pnl || 0) >= 0 ? "+" : ""}₹{Number(pos.pnl || 0).toLocaleString()}
                        </td>
                        <td style={{ padding: "8px 6px", textAlign: "center" }}>
                          <select
                            value={currentTgt}
                            onChange={(e) => setSelectedTargets({ ...selectedTargets, [pos.symbol]: e.target.value })}
                            style={{
                              padding: "2px 4px",
                              fontSize: 10,
                              background: "var(--surface2)",
                              border: "1px solid var(--border)",
                              color: "var(--green)",
                              borderRadius: 3,
                            }}
                          >
                            {TARGET_COLS.map((tc) => (
                              <option key={tc.key} value={tc.key}>
                                {tc.label}
                              </option>
                            ))}
                            <option value="CUSTOM">CUSTOM</option>
                          </select>
                        </td>
                        <td style={{ padding: "8px 6px", textAlign: "center" }}>
                          <button
                            type="button"
                            disabled={isImporting}
                            onClick={() => handleImport(pos)}
                            style={{
                              padding: "4px 8px",
                              fontSize: 10,
                              fontWeight: 700,
                              background: isAlreadyImported ? "rgba(56, 189, 248, 0.15)" : "rgba(0, 230, 118, 0.15)",
                              border: `1px solid ${isAlreadyImported ? "#38bdf8" : "var(--green)"}`,
                              color: isAlreadyImported ? "#38bdf8" : "var(--green)",
                              borderRadius: 3,
                              cursor: "pointer",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {isImporting ? "IMPORTING..." : isAlreadyImported ? "UPDATE ALGO" : "IMPORT TO ALGO"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: "12px 18px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            justifyContent: "flex-end",
            background: "var(--surface2)",
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "5px 14px",
              fontSize: 11,
              fontWeight: 600,
              background: "rgba(255,255,255,0.06)",
              border: "1px solid var(--border)",
              color: "var(--text)",
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            CLOSE
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Algo Trading Window Table (Fibonacci Automation + Custom Target) ─────────
function AlgoWindowTable({
  algoRows,
  isPaper = true,
  onToggleAlgo,
  onUpdateRow,
  onDeleteRow,
  onResetRow,
  onManualOrder,
  onKillRow,
  onOpenImportPositions,
}: {
  algoRows: any[];
  isPaper?: boolean;
  onToggleAlgo: (id: string, currentActive: boolean) => void;
  onUpdateRow: (id: string, updates: any) => void;
  onDeleteRow: (id: string) => void;
  onResetRow: (id: string) => void;
  onManualOrder: (id: string, side: "BUY" | "SELL") => void;
  onKillRow: (id: string) => void;
  onOpenImportPositions?: () => void;
}) {
  const activeCount = algoRows.filter((r) => r.is_algo_active).length;

  return (
    <div style={{ border: "1px solid var(--border)", background: "var(--surface)", marginBottom: 16 }}>
      {/* Header bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: "1px solid var(--border)", background: "rgba(0, 230, 118, 0.04)",
        flexWrap: "wrap", gap: 10
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5, color: "var(--green)" }}>
            ALGO TRADING WINDOW
          </span>
          <span className={`badge ${isPaper ? "badge-yellow" : "badge-green"}`} style={{ fontSize: 10, fontWeight: 700 }}>
            {isPaper ? "PAPER TRADING (SIMULATION)" : "LIVE DHAN BROKER"}
          </span>
          <span className="badge badge-green" style={{ fontSize: 10 }}>
            {activeCount} AUTOMATED ACTIVE
          </span>
          <span className="badge badge-gray" style={{ fontSize: 10 }}>
            {algoRows.length} SCRIPTS
          </span>
        </div>

        {onOpenImportPositions && (
          <button
            type="button"
            onClick={onOpenImportPositions}
            style={{
              padding: "5px 12px",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0.5,
              borderRadius: 4,
              cursor: "pointer",
              background: "rgba(56, 189, 248, 0.12)",
              border: "1px solid #38bdf8",
              color: "#38bdf8",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              transition: "all 0.15s",
            }}
            title="Fetch open positions from Dhan and import them into SELL ONLY mode for automated target exit"
          >
            IMPORT FROM DHAN POSITIONS
          </button>
        )}
      </div>

      {algoRows.length === 0 ? (
        <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
          No scripts in Algo Window. Click <strong style={{ color: "var(--green)" }}>+ ALGO</strong> on any symbol in the Equity or Options table above to add.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, fontFamily: "var(--font)" }}>
            <thead>
              <tr style={{ background: "var(--surface)", borderBottom: "2px solid var(--border)" }}>
                <th style={{ padding: "8px 6px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", width: 32 }}>#</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "left", minWidth: 105 }}>SCRIPT</th>
                <th style={{ padding: "8px 6px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", minWidth: 95 }}>MODE</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "right", minWidth: 80 }}>LTP</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", minWidth: 70 }}>SIGNAL</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--yellow)", textAlign: "center", minWidth: 145 }}>BUY TARGET / ENTRY</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "right", minWidth: 85 }}>ENTRY</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--red)", textAlign: "right", minWidth: 75 }}>SL</th>
                {TARGET_COLS.map((tc) => (
                  <th key={tc.key} style={{ padding: "8px 6px", fontSize: 10, letterSpacing: 1, color: tc.color, textAlign: "right", minWidth: 65 }}>
                    {tc.label}
                  </th>
                ))}
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--yellow)", textAlign: "center", minWidth: 145 }}>SELL TARGET / EXIT</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", minWidth: 95 }}>ALGO ON/OFF</th>
                <th style={{ padding: "8px 6px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", minWidth: 60 }}>QTY</th>
                <th style={{ padding: "8px 6px", fontSize: 10, letterSpacing: 1.2, color: "var(--yellow)", textAlign: "center", minWidth: 85 }}>TRADES</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "right", minWidth: 80 }}>BUYPRICE</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "right", minWidth: 85 }}>SELL TGT</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", minWidth: 150 }}>ACTIONS</th>
                <th style={{ padding: "8px 8px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", minWidth: 140 }}>STATUS</th>
                <th style={{ padding: "8px 4px", fontSize: 10, letterSpacing: 1.2, color: "var(--muted)", textAlign: "center", width: 32 }}></th>
              </tr>
            </thead>
            <tbody>
              {algoRows.map((r, idx) => {
                const isAuto = r.is_algo_active;
                const inPos = r.status === "IN_POSITION";
                const rowBg = inPos ? "rgba(0,230,118,0.04)" : "transparent";
                const isOpt = isOptionScript(r.symbol, r.segment);
                const normalizedTgt = normalizeTargetType(r.target_type);
                const normalizedEntry = normalizeEntryType(r.entry_type);
                const pClose = r.p_close;
                const chgPct = r.chg_pct;
                const isLtpUp = pClose != null && r.ltp != null ? r.ltp > pClose : (chgPct != null ? chgPct > 0 : false);
                const isLtpDown = pClose != null && r.ltp != null ? r.ltp < pClose : (chgPct != null ? chgPct < 0 : false);

                return (
                  <tr
                    key={r.id}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      background: rowBg,
                      borderLeft: isAuto ? "2px solid var(--green)" : "2px solid transparent",
                    }}
                  >
                    <td style={{ padding: "8px 6px", fontSize: 11, color: "var(--muted)", textAlign: "center" }}>
                      {idx + 1}
                    </td>
                    <td style={{ padding: "8px 8px", fontWeight: 700, color: "var(--text)" }}>
                      <div style={{ color: "var(--green)", fontSize: 12 }}>{r.symbol}</div>
                      <div style={{ fontSize: 9, color: "var(--muted)" }}>{r.segment || "NSE_EQ"}</div>
                    </td>

                    {/* Trade Mode column */}
                    <td style={{ padding: "8px 6px", textAlign: "center", minWidth: 95 }}>
                      <select
                        value={r.trade_mode || "FULL"}
                        onChange={(e) => {
                          const newMode = e.target.value;
                          const updates: any = { trade_mode: newMode };
                          if (newMode === "SELL_ONLY" && r.status === "IDLE" && r.buy_price) {
                            updates.status = "IN_POSITION";
                          }
                          onUpdateRow(r.id, updates);
                        }}
                        style={{
                          padding: "3px 4px",
                          fontSize: 10,
                          fontWeight: 700,
                          background: r.trade_mode === "BUY_ONLY" ? "rgba(0, 230, 118, 0.12)" : r.trade_mode === "SELL_ONLY" ? "rgba(251, 191, 36, 0.12)" : "var(--surface2)",
                          border: `1px solid ${r.trade_mode === "BUY_ONLY" ? "var(--green)" : r.trade_mode === "SELL_ONLY" ? "#f59e0b" : "var(--border)"}`,
                          color: r.trade_mode === "BUY_ONLY" ? "var(--green)" : r.trade_mode === "SELL_ONLY" ? "#fbbf24" : "var(--text)",
                          borderRadius: 3,
                          cursor: "pointer",
                          width: "100%",
                        }}
                        title="Trade Mode: FULL (Buy+Sell cycle), BUY ONLY (Auto entry, manual exit), or SELL ONLY (Auto profit target / SL on existing holding)"
                      >
                        <option value="FULL">FULL</option>
                        <option value="BUY_ONLY">BUY ONLY</option>
                        <option value="SELL_ONLY">SELL ONLY</option>
                      </select>
                    </td>

                    <td style={{ padding: "8px 8px", textAlign: "right", fontWeight: 700, fontSize: 12, whiteSpace: "nowrap" }}>
                      {r.ltp != null ? (
                        <span style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "flex-end",
                          gap: 4,
                          color: isLtpUp ? "var(--green)" : isLtpDown ? "var(--red)" : "var(--text)"
                        }}>
                          {isLtpUp && <span style={{ fontSize: 9, color: "var(--green)" }}>▲</span>}
                          {isLtpDown && <span style={{ fontSize: 9, color: "var(--red)" }}>▼</span>}
                          <span>₹{Number(r.ltp).toLocaleString()}</span>
                        </span>
                      ) : "—"}
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "center" }}>
                      <span className={`badge ${r.signal === "BUY" ? "badge-green" : r.signal === "SELL" ? "badge-red" : "badge-gray"}`} style={{ fontSize: 9, fontWeight: 700, minWidth: 38, textAlign: "center" }}>
                        {r.signal || "—"}
                      </span>
                    </td>

                    {/* BUY TARGET / ENTRY Dropdown + Custom Entry */}
                    <td style={{ padding: "8px 8px", textAlign: "center", minWidth: 145 }}>
                      {r.trade_mode === "SELL_ONLY" ? (
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                          <span className="badge badge-yellow" style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px" }}>
                            HOLDING
                          </span>
                          <span style={{ fontSize: 9, color: "var(--muted)" }}>NO BUY NEEDED</span>
                        </div>
                      ) : (
                        <>
                          <select
                            value={normalizedEntry}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (val === "CUSTOM") {
                                const initCustom = r.custom_entry || r.buy_entry_price || r.entry || r.ltp || 0;
                                onUpdateRow(r.id, { entry_type: "CUSTOM", custom_entry: initCustom });
                              } else {
                                onUpdateRow(r.id, { entry_type: val });
                              }
                            }}
                            style={{
                              width: "100%",
                              padding: "5px 8px",
                              fontSize: 11,
                              background: "var(--surface2)",
                              border: `1px solid ${r.entry_type === "CUSTOM" ? "#0284c7" : "rgba(0, 230, 118, 0.4)"}`,
                              color: r.entry_type === "CUSTOM" ? "#0284c7" : "var(--green)",
                              borderRadius: 3,
                              cursor: "pointer",
                              fontWeight: 700,
                            }}
                            title="Select trigger condition for BUY order (Formula Entry, T1-T9 Target level, or Custom Buy price)"
                          >
                            <option value="FORMULA">
                              ENTRY (FORMULA)
                            </option>
                            {TARGET_COLS.map((tc) => {
                              const sign = r.signal === "SELL" ? "-" : "+";
                              const pct = isOpt ? tc.pctOption : tc.pctEquity;
                              return (
                                <option key={tc.key} value={tc.key}>
                                  {`${tc.label} (${sign}${pct})`}
                                </option>
                              );
                            })}
                            <option value="CUSTOM">
                              CUSTOM BUY PRICE
                            </option>
                          </select>

                          {r.entry_type === "CUSTOM" && (
                            <div style={{ display: "flex", alignItems: "center", gap: 3, marginTop: 4 }}>
                              <span style={{ fontSize: 10, color: "#38bdf8", fontWeight: 700 }}>₹</span>
                              <input
                                type="number"
                                step="0.05"
                                placeholder="Buy Price"
                                defaultValue={r.custom_entry || r.buy_entry_price || r.entry || ""}
                                onBlur={(e) => {
                                  const num = parseFloat(e.target.value);
                                  if (!isNaN(num) && num > 0) {
                                    onUpdateRow(r.id, { custom_entry: num });
                                  }
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    const num = parseFloat((e.target as HTMLInputElement).value);
                                    if (!isNaN(num) && num > 0) {
                                      onUpdateRow(r.id, { custom_entry: num });
                                      (e.target as HTMLInputElement).blur();
                                    }
                                  }
                                }}
                                style={{
                                  width: "100%",
                                  padding: "2px 6px",
                                  fontSize: 11,
                                  background: "#0c1017",
                                  border: "1px solid #38bdf8",
                                  color: "#38bdf8",
                                  borderRadius: 3,
                                  textAlign: "right",
                                  fontWeight: 700,
                                }}
                                title="Enter custom buy trigger price and press Enter or click away"
                              />
                            </div>
                          )}
                        </>
                      )}
                    </td>

                    {/* Numeric ENTRY price column */}
                    <td style={{ padding: "8px 8px", textAlign: "right", fontSize: 12, fontWeight: 700, minWidth: 85 }}>
                      {r.trade_mode === "SELL_ONLY" ? (
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                          <span style={{ color: "var(--green)" }}>
                            {r.buy_price != null ? `₹${Number(r.buy_price).toLocaleString()}` : "—"}
                          </span>
                          <span style={{ fontSize: 9, color: "var(--muted)" }}>BOUGHT</span>
                        </div>
                      ) : (
                        <div>
                          <span style={{ color: r.entry_type === "CUSTOM" ? "#38bdf8" : (r.entry_type && r.entry_type !== "FORMULA" ? "#4ade80" : "var(--text)") }}>
                            ₹{Number(r.buy_entry_price ?? r.entry ?? 0).toLocaleString()}
                          </span>
                          {r.entry_type === "CUSTOM" && (
                            <span style={{ fontSize: 9, marginLeft: 3, color: "#38bdf8", fontWeight: 700 }}>[CUST]</span>
                          )}
                          {r.entry_type && r.entry_type !== "FORMULA" && r.entry_type !== "CUSTOM" && (
                            <span style={{ fontSize: 9, marginLeft: 3, color: "#4ade80", fontWeight: 700 }}>[{r.entry_type}]</span>
                          )}
                        </div>
                      )}
                    </td>

                    <td style={{ padding: "8px 8px", textAlign: "right", color: "var(--red)", fontSize: 12 }}>
                      {r.sl != null ? `₹${Number(r.sl).toLocaleString()}` : "—"}
                    </td>

                    {/* Target Columns T1 through T9 */}
                    {TARGET_COLS.map((tc) => {
                      const isArmed = isTargetArmed(r.target_type, tc.key);
                      const val = r[tc.aliasKey] ?? r[tc.altKey] ?? r[tc.key.toLowerCase()];
                      return (
                        <td
                          key={tc.key}
                          style={{
                            padding: "8px 6px",
                            textAlign: "right",
                            fontSize: 12,
                            color: isArmed ? "var(--green)" : "var(--muted)",
                            fontWeight: isArmed ? 700 : 400,
                            background: isArmed ? "rgba(0, 230, 118, 0.08)" : "transparent",
                            borderRight: isArmed ? "1px solid rgba(0, 230, 118, 0.25)" : "none",
                            borderLeft: isArmed ? "1px solid rgba(0, 230, 118, 0.25)" : "none",
                          }}
                          title={isArmed ? `Armed Target: ${tc.key}` : tc.key}
                        >
                          {val != null ? `₹${Number(val).toLocaleString()}` : "—"}
                        </td>
                      );
                    })}

                    {/* Active Target Selector / Kill Switch Dropdown + Custom Target */}
                    <td style={{ padding: "8px 8px", textAlign: "center", minWidth: 145 }}>
                      {r.trade_mode === "BUY_ONLY" && (
                        <div style={{ fontSize: 8, fontWeight: 700, color: "var(--muted)", marginBottom: 3, letterSpacing: 0.5 }}>
                          MANUAL EXIT MODE
                        </div>
                      )}
                      <select
                        value={normalizedTgt}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === "KILL") {
                            if (confirm(`Activate KILL SWITCH for ${r.symbol}? This will immediately exit open positions at market price and turn off algo.`)) {
                              onKillRow(r.id);
                            }
                          } else if (val === "CUSTOM") {
                            const initCustom = r.custom_target || r.sell_tgt || r.t1 || r.t11_8 || 0;
                            onUpdateRow(r.id, { target_type: "CUSTOM", custom_target: initCustom, sell_tgt: initCustom });
                          } else {
                            onUpdateRow(r.id, { target_type: val });
                          }
                        }}
                        style={{
                          width: "100%",
                          padding: "5px 8px",
                          fontSize: 11,
                          background: r.target_type === "KILL" ? "rgba(255,40,80,0.18)" : "var(--surface2)",
                          border: `1px solid ${r.target_type === "KILL" ? "var(--red)" : r.target_type === "CUSTOM" ? "#0284c7" : "rgba(0, 230, 118, 0.4)"}`,
                          color: r.target_type === "KILL" ? "var(--red)" : r.target_type === "CUSTOM" ? "#0284c7" : "var(--green)",
                          borderRadius: 3,
                          cursor: "pointer",
                          fontWeight: 700,
                        }}
                        title="Select active target level or trigger instant Kill Switch"
                      >
                        {TARGET_COLS.map((tc) => {
                          const sign = r.signal === "SELL" ? "-" : "+";
                          const pct = isOpt ? tc.pctOption : tc.pctEquity;
                          return (
                            <option key={tc.key} value={tc.key}>
                              {`${tc.label} (${sign}${pct})`}
                            </option>
                          );
                        })}
                        <option value="CUSTOM">CUSTOM TARGET</option>
                        <option value="KILL" style={{ color: "var(--red)", fontWeight: 800 }}>KILL SWITCH (EXIT NOW)</option>
                      </select>

                      {r.target_type === "CUSTOM" && (
                        <div style={{ display: "flex", alignItems: "center", gap: 3, marginTop: 4 }}>
                          <span style={{ fontSize: 10, color: "#38bdf8", fontWeight: 700 }}>₹</span>
                          <input
                            type="number"
                            step="0.05"
                            placeholder="Target Price"
                            defaultValue={r.custom_target || r.sell_tgt || ""}
                            onBlur={(e) => {
                              const num = parseFloat(e.target.value);
                              if (!isNaN(num) && num > 0) {
                                onUpdateRow(r.id, { custom_target: num, sell_tgt: num });
                              }
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                const num = parseFloat((e.target as HTMLInputElement).value);
                                if (!isNaN(num) && num > 0) {
                                  onUpdateRow(r.id, { custom_target: num, sell_tgt: num });
                                  (e.target as HTMLInputElement).blur();
                                }
                              }
                            }}
                            style={{
                              width: "100%",
                              padding: "2px 6px",
                              fontSize: 11,
                              background: "#0c1017",
                              border: "1px solid #38bdf8",
                              color: "#38bdf8",
                              borderRadius: 3,
                              textAlign: "right",
                              fontWeight: 700,
                            }}
                            title="Enter custom exit target price and press Enter or click away"
                          />
                        </div>
                      )}
                    </td>

                    {/* ALGO ON/OFF Button */}
                    <td style={{ padding: "8px 8px", textAlign: "center" }}>
                      <button
                        type="button"
                        onClick={() => onToggleAlgo(r.id, r.is_algo_active)}
                        style={{
                          padding: "4px 8px",
                          fontSize: 10,
                          fontWeight: 700,
                          letterSpacing: 0.5,
                          borderRadius: 3,
                          cursor: "pointer",
                          background: isAuto ? "rgba(0, 230, 118, 0.18)" : "var(--surface2)",
                          border: `1px solid ${isAuto ? "var(--green)" : "var(--border)"}`,
                          color: isAuto ? "var(--green)" : "var(--muted)",
                          transition: "all 0.15s",
                        }}
                      >
                        {isAuto ? "ALGO ON" : "ALGO OFF"}
                      </button>
                    </td>

                    {/* QTY */}
                    <td style={{ padding: "8px 4px", textAlign: "center" }}>
                      <input
                        type="number"
                        min={1}
                        value={r.quantity}
                        onChange={(e) => onUpdateRow(r.id, { quantity: Number(e.target.value) })}
                        style={{
                          width: 48,
                          padding: "3px 4px",
                          fontSize: 11,
                          background: "var(--surface2)",
                          border: "1px solid var(--border)",
                          color: "var(--text)",
                          borderRadius: 3,
                          textAlign: "center",
                        }}
                      />
                    </td>

                    {/* NUMBER OF TRADE 1 to 5 */}
                    <td style={{ padding: "8px 4px", textAlign: "center" }}>
                      <select
                        value={r.number_of_trades}
                        onChange={(e) => onUpdateRow(r.id, { number_of_trades: Number(e.target.value) })}
                        style={{
                          padding: "3px 4px",
                          fontSize: 11,
                          background: "var(--surface2)",
                          border: "1px solid var(--border)",
                          color: "var(--yellow)",
                          borderRadius: 3,
                          cursor: "pointer",
                          fontWeight: 600,
                        }}
                      >
                        {[1, 2, 3, 4, 5].map((n) => (
                          <option key={n} value={n}>
                            {n} {n === 1 ? "TRD" : "TRDS"}
                          </option>
                        ))}
                      </select>
                    </td>

                    {/* BUYPRICE */}
                    <td style={{ padding: "8px 8px", textAlign: "right", color: r.buy_price ? "var(--green)" : "var(--muted)", fontSize: 12 }}>
                      {r.buy_price != null ? `₹${Number(r.buy_price).toLocaleString()}` : "—"}
                    </td>

                    {/* SELL TGT */}
                    <td style={{ padding: "8px 8px", textAlign: "right", color: r.sell_tgt ? (r.target_type === "CUSTOM" ? "#38bdf8" : "var(--green)") : "var(--muted)", fontSize: 12, fontWeight: 700 }}>
                      {r.sell_tgt != null ? (
                        <span>
                          ₹{Number(r.sell_tgt).toLocaleString()}
                          {r.target_type === "CUSTOM" && <span style={{ fontSize: 9, marginLeft: 3, color: "#38bdf8" }}>[CUST]</span>}
                        </span>
                      ) : r.trade_mode === "BUY_ONLY" ? (
                        <span style={{ fontSize: 10, color: "var(--muted)" }}>MANUAL</span>
                      ) : "—"}
                    </td>

                    {/* ACTIONS: Manual BUY/SELL + Instant Kill Switch */}
                    <td style={{ padding: "8px 8px", textAlign: "center", whiteSpace: "nowrap" }}>
                      <div style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>
                        {isAuto ? (
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              padding: "3px 6px",
                              fontSize: 9,
                              fontWeight: 700,
                              color: "var(--green)",
                              background: "rgba(0, 230, 118, 0.08)",
                              border: "1px solid rgba(0, 230, 118, 0.3)",
                              borderRadius: 3,
                            }}
                          >
                            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--green)" }} />
                            AUTO
                          </span>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => onManualOrder(r.id, "BUY")}
                              style={{
                                padding: "3px 6px",
                                fontSize: 9,
                                fontWeight: 700,
                                cursor: "pointer",
                                background: "rgba(0, 230, 118, 0.16)",
                                border: "1px solid var(--green)",
                                color: "var(--green)",
                                borderRadius: 3,
                              }}
                              title={`Manual Buy ${r.symbol}`}
                            >
                              BUY
                            </button>
                            <button
                              type="button"
                              onClick={() => onManualOrder(r.id, "SELL")}
                              style={{
                                padding: "3px 6px",
                                fontSize: 9,
                                fontWeight: 700,
                                cursor: "pointer",
                                background: "rgba(255, 68, 102, 0.16)",
                                border: "1px solid var(--red)",
                                color: "var(--red)",
                                borderRadius: 3,
                              }}
                              title={`Manual Sell ${r.symbol}`}
                            >
                              SELL
                            </button>
                          </>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            if (confirm(`Kill position and pause algo for ${r.symbol}?`)) {
                              onKillRow(r.id);
                            }
                          }}
                          style={{
                            padding: "3px 6px",
                            fontSize: 9,
                            fontWeight: 700,
                            cursor: "pointer",
                            background: "rgba(255, 68, 102, 0.12)",
                            border: "1px solid rgba(255, 68, 102, 0.4)",
                            color: "var(--red)",
                            borderRadius: 3,
                          }}
                          title={`Emergency exit and stop algo for ${r.symbol}`}
                        >
                          KILL
                        </button>
                      </div>
                    </td>

                    {/* STATUS */}
                    <td style={{ padding: "8px 8px", textAlign: "center" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "center" }}>
                        <span
                          className={`badge ${
                            r.status === "IN_POSITION"
                              ? "badge-green"
                              : r.status === "COMPLETED"
                              ? "badge-yellow"
                              : r.status === "WAITING_RETURN"
                              ? "badge-yellow"
                              : "badge-gray"
                          }`}
                          style={{ fontSize: 9, fontWeight: 700 }}
                        >
                          {r.status}
                        </span>
                        {r.trades_completed > 0 && (
                          <span style={{ fontSize: 9, color: "var(--muted)" }}>
                            {r.trades_completed}/{r.number_of_trades} trades
                          </span>
                        )}
                        {r.pnl != null && r.pnl !== 0 && (
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              color: r.pnl >= 0 ? "var(--green)" : "var(--red)",
                            }}
                          >
                            {r.pnl >= 0 ? "+" : ""}₹{Number(r.pnl).toLocaleString()}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Delete Script from Window */}
                    <td style={{ padding: "8px 4px", textAlign: "center" }}>
                      <button
                        type="button"
                        onClick={() => {
                          if (confirm(`Remove ${r.symbol} from Algo Window?`)) {
                            onDeleteRow(r.id);
                          }
                        }}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "rgba(255,68,102,0.6)",
                          cursor: "pointer",
                          fontSize: 13,
                          padding: 2,
                        }}
                        title={`Remove ${r.symbol} from Algo Window`}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Terminal Table ────────────────────────────────────────────────────────────
function TerminalTable({ title, book = "equity", watchlist, liveData, termRowMap, visibleCols, columnValues, isAdmin,
  onRemoveSymbol, onExitRow, onFormulaRow, onOrder, onAddToAlgo, instrMap }: {
  title: string;
  book?: string;
  watchlist: string[]; liveData: Record<string,any>; termRowMap: Record<string,any>;
  visibleCols: any[]; columnValues: Record<string, Record<string, any>>; isAdmin: boolean;
  onRemoveSymbol:(s:string)=>void; onExitRow:(id:string)=>void;
  onFormulaRow:(id:string,sym:string)=>void;
  onOrder:(sym:string,inst:{security_id:string,segment:string},prefillSide?:string,prefillPrice?:number|null)=>void;
  onAddToAlgo:(sym:string, segment?: string, exchange?: string, token?: string)=>void;
  instrMap: Record<string,{security_id:string; segment:string; exchange?: string}>;
}) {
  const signalColIdx = visibleCols.findIndex((col: any) => col.name?.toUpperCase() === "SIGNAL");

  return (
    <div style={{border:"1px solid var(--border)", background:"var(--surface)", marginBottom:10}}>
      <div style={{
        display:"flex", alignItems:"center", justifyContent:"space-between",
        padding:"8px 12px", borderBottom:"1px solid var(--border)", background:"var(--surface2)",
        flexWrap: "wrap", gap: 10
      }}>
        <div style={{display:"flex", alignItems:"center", gap:8}}>
          <span style={{
            fontSize:11, fontWeight:700, letterSpacing:1.5,
            color: title.includes("OPTIONS") ? "var(--yellow)" : title.includes("MCX") ? "#08b6de" : "var(--green)"
          }}>
            {title.includes("WATCHLIST") ? title : `${title} WATCHLIST`}
          </span>
        </div>
      </div>
      <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontSize:13,fontFamily:"var(--font)"}}>
        <thead>
          <tr style={{background:"var(--surface)",borderBottom:"2px solid var(--border)"}}>
            <th style={{
              position:"sticky", left:0, zIndex:20,
              background:"var(--surface)",
              padding:"6px 4px", fontSize:10, letterSpacing:1.2, color:"var(--muted)",
              borderRight:"1px solid var(--border)", width:46, minWidth:46, maxWidth:46, textAlign:"center"
            }}>#</th>
            <th style={{
              position:"sticky", left:46, zIndex:20,
              background:"var(--surface)",
              padding:"8px 10px", fontSize:10, letterSpacing:1.5, color:"var(--muted)",
              borderRight:"2px solid var(--border)", width:140, minWidth:140, maxWidth:140, textAlign:"left",
              boxShadow:"3px 0 6px -2px rgba(0,0,0,0.35)"
            }}>SYMBOL</th>
            {visibleCols.map((col:any, cIdx:number) => {
              const isSignalCol = cIdx === signalColIdx;
              return (
                <Fragment key={col.id || col.col_key || cIdx}>
                  {isSignalCol && (
                    <th key="order-col-header" style={{
                      padding:"8px 10px", fontSize:10, letterSpacing:1.5,
                      color:"var(--muted)", borderRight:"1px solid var(--border)",
                      minWidth:110, textAlign:"center"
                    }}>
                      ORDER
                    </th>
                  )}
                  <th style={{
                    padding:"8px 8px", fontSize:10, letterSpacing:1.5, whiteSpace:"nowrap",
                    color:col.col_type==="custom"||col.col_type==="formula"?"var(--yellow)":"var(--muted)",
                    borderRight:"1px solid var(--border)", minWidth:col.width||80, textAlign:"left",
                  }}>
                    <span>{columnTitle(col.name)}</span>
                  </th>
                </Fragment>
              );
            })}
            <th style={{padding:"8px 6px",fontSize:9,color:"var(--muted)",minWidth:70,textAlign:"center"}}>ACTIONS</th>
          </tr>
        </thead>
        <tbody>
          {watchlist.map((sym, idx) => {
            const live  = liveData[sym] ?? {};
            const trow  = termRowMap[sym];
            const ltp   = live.ltp ?? trow?.ltp ?? null;
            const chg   = live.change_pct ?? null;
            const pClose = live.p_close ?? live.prev_close ?? null;
            const isLtpUp = pClose != null && ltp != null ? ltp > pClose : (chg != null ? chg > 0 : false);
            const isLtpDown = pClose != null && ltp != null ? ltp < pClose : (chg != null ? chg < 0 : false);
            const pos   = (chg ?? 0) >= 0;
            const inPos = trow?.status === "active";
            const rowBg = inPos ? "rgba(0,255,136,0.06)" : "var(--surface)";
            const pnl   = trow?.pnl ?? null;

            function getCellValue(col: any): {color:string, formatted:string} {
              let value: any = null;
              let color = "var(--text)";

              if (col.col_type==="custom"||col.col_type==="formula") {
                value = columnValues?.[sym]?.[col.name] ?? null;
                color = getColColor(value, col.color_rules);
              } else {
                switch(col.col_key) {
                  case "open":       value=live.open; break;
                  case "high":       value=live.high; color="var(--green)"; break;
                  case "low":        value=live.low;  color="var(--red)"; break;
                  case "close":      value=live.close; break;
                  case "p_high":     value=live.p_high ?? null; color="var(--green)"; break;
                  case "p_low":      value=live.p_low ?? null;  color="var(--red)"; break;
                  case "p_close":    value=live.p_close ?? live.prev_close ?? null; break;
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
                onMouseEnter={e=>(e.currentTarget.style.background=inPos?"rgba(0,255,136,0.06)":"var(--surface2)")}
                onMouseLeave={e=>(e.currentTarget.style.background=inPos?"rgba(0,255,136,0.03)":"transparent")}
              >
                <td style={{
                  position:"sticky", left:0, zIndex:10,
                  background:rowBg,
                  padding:"4px 4px", fontSize:11, color:"var(--muted)",
                  borderRight:"1px solid var(--border)", width:46, minWidth:46, maxWidth:46,
                  textAlign:"center", fontWeight:600
                }}>
                  <div style={{ fontSize: 11, lineHeight: 1 }}>{idx+1}</div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      const inst = ((typeof instrMap !== "undefined" ? instrMap[sym] : null) || SECURITY_IDS[sym]) as any;
                      onAddToAlgo(sym, inst?.segment, inst?.exchange, inst?.security_id);
                    }}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 22,
                      height: 18,
                      marginTop: 3,
                      fontSize: 9,
                      fontWeight: 800,
                      cursor: "pointer",
                      background: "rgba(0, 230, 118, 0.12)",
                      border: "1px solid rgba(0, 230, 118, 0.4)",
                      color: "var(--green)",
                      borderRadius: 3,
                      padding: 0,
                      lineHeight: 1,
                    }}
                    title={`Add ${sym} to Algo Trading Window`}
                  >
                    +A
                  </button>
                </td>
                <td style={{
                  position:"sticky", left:46, zIndex:10,
                  background:rowBg,
                  padding:"6px 10px", borderRight:"2px solid var(--border)",
                  width:140, minWidth:140, maxWidth:140,
                  boxShadow:"3px 0 6px -2px rgba(0,0,0,0.35)"
                }}>
                  <div style={{fontWeight:700,color:"var(--green)",fontSize:13}}>{sym}</div>
                </td>
                {visibleCols.map((col:any, cIdx:number) => {
                  const {color, formatted} = getCellValue(col);
                  const isSignalCol = cIdx === signalColIdx;
                  return (
                    <Fragment key={col.id || col.col_key || cIdx}>
                      {isSignalCol && (
                        <td key="order-col-cell" style={{
                          padding:"4px 8px", borderRight:"1px solid var(--border)",
                          textAlign:"center", whiteSpace:"nowrap"
                        }}>
                          <div style={{display:"inline-flex", gap:5, alignItems:"center"}}>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                const inst = (typeof instrMap !== "undefined" ? instrMap[sym] : null) || SECURITY_IDS[sym];
                                if (inst) onOrder(sym, inst, "BUY", ltp);
                              }}
                              style={{
                                padding:"3px 9px", fontSize:10, fontWeight:700, cursor:"pointer",
                                background:"rgba(47, 158, 143, 0.16)", border: "1px solid var(--green)",
                                color:"var(--green)", borderRadius:3, transition:"all 0.15s",
                              }}
                              title={`Buy ${sym}`}
                            >
                              BUY
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                const inst = (typeof instrMap !== "undefined" ? instrMap[sym] : null) || SECURITY_IDS[sym];
                                if (inst) onOrder(sym, inst, "SELL", ltp);
                              }}
                              style={{
                                padding:"3px 9px", fontSize:10, fontWeight:700, cursor:"pointer",
                                background:"rgba(225, 91, 100, 0.16)", border: "1px solid var(--red)",
                                color:"var(--red)", borderRadius:3, transition:"all 0.15s",
                              }}
                              title={`Sell ${sym}`}
                            >
                              SELL
                            </button>
                          </div>
                        </td>
                      )}
                      <td style={{
                        padding:"7px 10px",
                        color: col.col_key==="ltp" ? (isLtpUp ? "var(--green)" : isLtpDown ? "var(--red)" : "var(--text)") : color,
                        borderRight:"1px solid var(--border)",
                        fontWeight:col.col_key==="ltp"?"700":"400",
                        fontSize:col.col_key==="ltp"?"14px":"13px",
                        whiteSpace: col.col_key==="ltp" ? "nowrap" : undefined,
                      }}>
                        {col.col_key === "ltp" && ltp != null ? (
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            {isLtpUp && <span style={{ fontSize: 9, color: "var(--green)" }}>▲</span>}
                            {isLtpDown && <span style={{ fontSize: 9, color: "var(--red)" }}>▼</span>}
                            <span>{formatted}</span>
                          </span>
                        ) : (
                          formatted
                        )}
                      </td>
                    </Fragment>
                  );
                })}
                <td style={{padding:"6px 8px"}}>
                  <div style={{display:"flex",gap:4, alignItems:"center"}}>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        const seg = book === "option" ? "NSE_FNO" : (instrMap[sym]?.segment || "NSE_EQ");
                        const exch = book === "option" ? "NFO" : ((instrMap[sym] as any)?.exchange || "NSE");
                        onAddToAlgo(sym, seg, exch);
                      }}
                      style={{
                        padding:"2px 7px", fontSize:10, fontWeight:700, cursor:"pointer",
                        background:"rgba(0,230,118,0.12)", border:"1px solid var(--green)",
                        color:"var(--green)", borderRadius:3, fontFamily:"var(--font)",
                      }}
                      title={`Add ${sym} to Algo Trading Window`}
                    >
                      + ALGO
                    </button>
                    {inPos&&trow&&(
                      <button className="exit-btn"
                        style={{padding:"2px 7px",fontSize:10,color:"var(--red)",
                          borderColor:"rgba(255,68,102,0.4)"}}
                        onClick={()=>onExitRow(trow.id)}>EXIT</button>
                    )}
                    {signalColIdx === -1 && (() => {
                        const inst = (typeof instrMap !== "undefined" ? instrMap[sym] : null) || SECURITY_IDS[sym];
                        if (!inst) return null;
                        return <>
                          <button onClick={e=>{e.stopPropagation();onOrder(sym, inst, "BUY", ltp);}}
                            style={{padding:"2px 8px",fontSize:10,cursor:"pointer",fontWeight:700,
                              background:"rgba(0,255,136,0.1)",border:"1px solid rgba(0,255,136,0.3)",
                              color:"var(--green)",fontFamily:"var(--font)"}}>B</button>
                          <button onClick={e=>{e.stopPropagation();onOrder(sym, inst, "SELL", ltp);}}
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
                        title="Set strategy formula">ƒ</button>
                    )}
                    <button onClick={()=>onRemoveSymbol(sym)}
                      style={{padding:"2px 5px",fontSize:11,background:"transparent",
                        border:"none",color:"var(--muted)",cursor:"pointer",opacity:0.5}}>×</button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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
      toast.success(`${side} order placed — ID: ${res.data?.order_id}`);
      notifyOrder(side, symbol, qty, orderType === "LIMIT" ? price : ltp || undefined);
      qc.invalidateQueries({queryKey:["orderbook"]});
      onClose();
    },
    onError: (e: any) => {
      const d = e.response?.data?.detail;
      const msg = Array.isArray(d) ? d.map((x:any) => x.msg || JSON.stringify(x)).join(", ") : typeof d === "string" ? d : d?.error_message || JSON.stringify(d) || "Order failed";
      toast.error(msg);
      notifyError("ORDER REJECTED", `${symbol} ${side}: ${msg}`);
      setConfirm(false);
    },
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
          }}>×</button>
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
                Confirm {side} {qty} shares of {symbol}
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