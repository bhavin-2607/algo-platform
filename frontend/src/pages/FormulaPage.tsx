import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

const INDICATOR_HELP = [
  { fn: "ma(20)",          desc: "Simple moving average, period 20" },
  { fn: "ema(9)",          desc: "Exponential moving average, period 9" },
  { fn: "rsi(14)",         desc: "RSI oscillator, period 14 (0-100)" },
  { fn: "vwap()",          desc: "Volume weighted average price" },
  { fn: "atr(14)",         desc: "Average true range" },
  { fn: "bb_upper(20)",    desc: "Bollinger Band upper (20, 2σ)" },
  { fn: "bb_lower(20)",    desc: "Bollinger Band lower (20, 2σ)" },
  { fn: "supertrend(7,3)", desc: "Returns +1 bullish, -1 bearish" },
];

const EXAMPLE_FORMULAS = [
  {
    name: "MA Crossover (Golden Cross)",
    entry_long:  "ma(9) > ma(21)",
    exit_long:   "ma(9) < ma(21)",
    entry_short: "ma(9) < ma(21)",
    exit_short:  "ma(9) > ma(21)",
  },
  {
    name: "RSI Oversold/Overbought",
    entry_long:  "rsi(14) < 30 AND close > ma(50)",
    exit_long:   "rsi(14) > 70",
    entry_short: "rsi(14) > 70 AND close < ma(50)",
    exit_short:  "rsi(14) < 30",
  },
  {
    name: "VWAP Breakout",
    entry_long:  "close > vwap() AND volume > 300000",
    exit_long:   "close < vwap()",
    entry_short: "",
    exit_short:  "",
  },
  {
    name: "Supertrend",
    entry_long:  "supertrend(7, 3) > 0",
    exit_long:   "supertrend(7, 3) < 0",
    entry_short: "supertrend(7, 3) < 0",
    exit_short:  "supertrend(7, 3) > 0",
  },
];

const SYMBOLS = ["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","WIPRO","SBIN","TATAMOTORS","NIFTY50"];

export default function FormulaPage() {
  const [tab, setTab] = useState<"strategies"|"positions">("strategies");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">FORMULA STRATEGIES</h1>
          <p className="page-sub">No-code condition-based strategies with Target / SL / Trailing SL</p>
        </div>
        <div className="tab-switcher">
          <button className={`tab-btn${tab==="strategies"?" active":""}`} onClick={()=>setTab("strategies")}>STRATEGIES</button>
          <button className={`tab-btn${tab==="positions" ?" active":""}`} onClick={()=>setTab("positions")}>POSITIONS</button>
        </div>
      </div>
      {tab==="strategies" && <StrategiesTab />}
      {tab==="positions"  && <PositionsTab />}
    </Layout>
  );
}

/* ── STRATEGIES TAB ──────────────────────────────────────────────────────── */
function StrategiesTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing,  setEditing]  = useState<any>(null);

  const { data: strategies, isLoading } = useQuery({
    queryKey: ["formula-strategies"],
    queryFn: () => api.get("/formula").then(r => r.data),
    refetchInterval: 10_000,
  });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/formula/${id}`),
    onSuccess: () => { toast.success("Strategy deleted"); qc.invalidateQueries({queryKey:["formula-strategies"]}); },
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => api.post(`/formula/${id}/start`),
    onSuccess: () => { toast.success("Strategy started"); qc.invalidateQueries({queryKey:["formula-strategies"]}); },
    onError: (e:any) => toast.error(e.response?.data?.detail || "Failed to start"),
  });

  const stopMutation = useMutation({
    mutationFn: (id: string) => api.post(`/formula/${id}/stop`),
    onSuccess: () => { toast.success("Strategy stopped"); qc.invalidateQueries({queryKey:["formula-strategies"]}); },
  });

  return (
    <div>
      <div style={{ display:"flex", justifyContent:"flex-end", marginBottom:16 }}>
        <button className="connect-btn" onClick={()=>{ setEditing(null); setShowForm(v=>!v); }}>
          {showForm ? "✕ CANCEL" : "+ NEW FORMULA STRATEGY"}
        </button>
      </div>

      {(showForm || editing) && (
        <FormulaForm
          brokers={brokers??[]}
          initial={editing}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({queryKey:["formula-strategies"]}); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      {isLoading && <div style={{color:"var(--muted)",padding:20,fontSize:12}}>Loading...</div>}

      <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
        {strategies?.map((s:any) => (
          <div key={s.id} className={`card${s.is_running?" strategy-card active":""}`}
            style={s.is_running?{borderColor:"rgba(0,255,136,0.4)"}:{}}>
            <div className="card-header">
              <div style={{display:"flex",alignItems:"center",gap:10}}>
                <span className="card-title">{s.name}</span>
                <span className="symbol" style={{fontSize:12}}>{s.symbol}</span>
                <span className={`badge ${s.paper_trading?"badge-yellow":"badge-red"}`}>
                  {s.paper_trading?"PAPER":"LIVE"}
                </span>
                <span className={`badge ${s.is_running?"badge-green":"badge-gray"}`}>
                  {s.is_running?"● RUNNING":"○ IDLE"}
                </span>
              </div>
              <div style={{display:"flex",gap:8}}>
                <button className="exit-btn" onClick={()=>{setEditing(s);setShowForm(false);}}>EDIT</button>
                {s.is_running
                  ? <button className="strategy-btn btn-stop" style={{flex:"none",padding:"4px 14px"}}
                      onClick={()=>stopMutation.mutate(s.id)}>⏹ STOP</button>
                  : <button className="strategy-btn btn-start" style={{flex:"none",padding:"4px 14px"}}
                      onClick={()=>startMutation.mutate(s.id)}>▶ START</button>
                }
                <button className="exit-btn" style={{color:"var(--red)",borderColor:"rgba(255,68,102,0.3)"}}
                  onClick={()=>deleteMutation.mutate(s.id)}>DELETE</button>
              </div>
            </div>

            <div style={{padding:"16px 20px"}}>
              {/* Condition grid */}
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
                {s.entry_long  && <ConditionChip label="ENTRY LONG"  expr={s.entry_long}  color="green" />}
                {s.exit_long   && <ConditionChip label="EXIT LONG"   expr={s.exit_long}   color="muted" />}
                {s.entry_short && <ConditionChip label="ENTRY SHORT" expr={s.entry_short} color="red"   />}
                {s.exit_short  && <ConditionChip label="EXIT SHORT"  expr={s.exit_short}  color="muted" />}
              </div>

              {/* Settings row */}
              <div style={{display:"flex",gap:16,flexWrap:"wrap"}}>
                <Chip label="QTY"       value={s.quantity} />
                <Chip label="TIMEFRAME" value={`${s.timeframe_minutes}m`} />
                {s.target_pct  && <Chip label="TARGET"  value={`${s.target_pct}%`} color="green" />}
                {s.sl_pct      && <Chip label="SL"      value={`${s.sl_pct}%`}    color="red"   />}
                {s.trailing_sl && <Chip label="TRAIL SL" value={`${s.trail_pct}%`} color="yellow" />}
              </div>
            </div>
          </div>
        ))}

        {!isLoading && !strategies?.length && (
          <div className="card">
            <div style={{padding:"48px 24px",textAlign:"center"}}>
              <div style={{fontSize:32,marginBottom:12}}>⟳</div>
              <div style={{fontSize:14,fontWeight:700,marginBottom:8}}>No formula strategies yet</div>
              <div style={{fontSize:12,color:"var(--muted)"}}>
                Create one above — define entry/exit conditions in plain English.
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Indicator reference */}
      <div className="card" style={{marginTop:24}}>
        <div className="card-header"><span className="card-title">AVAILABLE INDICATORS</span></div>
        <div style={{padding:"12px 20px 20px",display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))",gap:8}}>
          {INDICATOR_HELP.map(i=>(
            <div key={i.fn} style={{padding:"10px 12px",background:"var(--surface2)",border:"1px solid var(--border)"}}>
              <code style={{color:"var(--green)",fontSize:12}}>{i.fn}</code>
              <div style={{fontSize:11,color:"var(--muted)",marginTop:4}}>{i.desc}</div>
            </div>
          ))}
        </div>
        <div style={{padding:"0 20px 16px",fontSize:11,color:"var(--muted)"}}>
          Price variables: <code style={{color:"var(--green)"}}>open, high, low, close, volume, ltp</code>
          &nbsp;· Operators: <code style={{color:"var(--green)"}}>AND, OR, NOT, &gt;, &lt;, &gt;=, &lt;=, ==</code>
        </div>
      </div>
    </div>
  );
}

/* ── FORMULA FORM ────────────────────────────────────────────────────────── */
function FormulaForm({ brokers, initial, onSaved, onCancel }: any) {
  const [form, setForm] = useState({
    name:              initial?.name             ?? "",
    symbol:            initial?.symbol           ?? "RELIANCE",
    exchange:          initial?.exchange         ?? "NSE",
    token:             initial?.token            ?? "2885",
    entry_long:        initial?.entry_long       ?? "",
    exit_long:         initial?.exit_long        ?? "",
    entry_short:       initial?.entry_short      ?? "",
    exit_short:        initial?.exit_short       ?? "",
    quantity:          initial?.quantity         ?? 1,
    timeframe_minutes: initial?.timeframe_minutes ?? 5,
    target_pct:        initial?.target_pct       ?? "",
    sl_pct:            initial?.sl_pct           ?? "",
    trailing_sl:       initial?.trailing_sl      ?? false,
    trail_pct:         initial?.trail_pct        ?? "",
    paper_trading:     initial?.paper_trading    ?? true,
    broker_account_id: initial?.broker_account_id ?? "",
  });

  const [validating, setValidating] = useState<Record<string,string>>({});
  const set = (k:string) => (e:any) => setForm(f=>({...f,[k]:e.target?.value??e}));

  async function validateField(field: string, expr: string) {
    if (!expr) return;
    try {
      const res = await api.post("/formula/validate-formula", { expression: expr });
      setValidating(v=>({...v,[field]:res.data.valid?"✓":"✗ "+res.data.error}));
    } catch { setValidating(v=>({...v,[field]:"✗ error"})); }
  }

  function applyExample(ex: any) {
    setForm(f=>({...f,
      entry_long:  ex.entry_long,
      exit_long:   ex.exit_long,
      entry_short: ex.entry_short,
      exit_short:  ex.exit_short,
      name:        f.name || ex.name,
    }));
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        ...form,
        quantity:          parseInt(String(form.quantity)),
        timeframe_minutes: parseInt(String(form.timeframe_minutes)),
        target_pct:        form.target_pct ? parseFloat(String(form.target_pct)) : null,
        sl_pct:            form.sl_pct     ? parseFloat(String(form.sl_pct))     : null,
        trail_pct:         form.trail_pct  ? parseFloat(String(form.trail_pct))  : null,
        broker_account_id: form.broker_account_id || null,
      };
      return initial
        ? api.put(`/formula/${initial.id}`, payload)
        : api.post("/formula", payload);
    },
    onSuccess: () => { toast.success(initial?"Strategy updated":"Strategy created"); onSaved(); },
    onError: (e:any) => toast.error(e.response?.data?.detail || "Save failed"),
  });

  return (
    <div className="card" style={{marginBottom:20}}>
      <div className="card-header">
        <span className="card-title">{initial?"EDIT FORMULA STRATEGY":"NEW FORMULA STRATEGY"}</span>
      </div>
      <div style={{padding:"20px 20px 8px"}}>

        {/* Example templates */}
        <div style={{marginBottom:20}}>
          <div style={{fontSize:10,letterSpacing:2,color:"var(--muted)",marginBottom:8}}>QUICK TEMPLATES</div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            {EXAMPLE_FORMULAS.map(ex=>(
              <button key={ex.name} onClick={()=>applyExample(ex)} style={{
                padding:"6px 12px",fontSize:11,fontFamily:"var(--font)",cursor:"pointer",
                background:"transparent",border:"1px solid var(--border)",
                color:"var(--muted)",transition:"all 0.15s",
              }}
              onMouseEnter={e=>{(e.target as any).style.color="var(--green)";(e.target as any).style.borderColor="rgba(0,255,136,0.3)";}}
              onMouseLeave={e=>{(e.target as any).style.color="var(--muted)";(e.target as any).style.borderColor="var(--border)";}}>
                {ex.name}
              </button>
            ))}
          </div>
        </div>

        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
          <FInput label="STRATEGY NAME" value={form.name} onChange={set("name")} />
          <div className="field">
            <label className="field-label">SYMBOL</label>
            <select className="field-input" value={form.symbol} onChange={set("symbol")}
              style={{background:"rgba(0,255,136,0.04)",color:"var(--text)",fontFamily:"var(--font)"}}>
              {SYMBOLS.map(s=><option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
          <div className="field">
            <label className="field-label">TIMEFRAME</label>
            <select className="field-input" value={form.timeframe_minutes} onChange={set("timeframe_minutes")}
              style={{background:"rgba(0,255,136,0.04)",color:"var(--text)",fontFamily:"var(--font)"}}>
              {[1,3,5,10,15,30,60].map(t=><option key={t} value={t}>{t} min</option>)}
            </select>
          </div>
          <FInput label="QUANTITY" value={form.quantity} onChange={set("quantity")} type="number" />
        </div>

        {/* Condition fields */}
        <div style={{fontSize:10,letterSpacing:2,color:"var(--green)",margin:"16px 0 8px"}}>ENTRY / EXIT CONDITIONS</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
          <FormulaField label="ENTRY LONG (BUY)" value={form.entry_long}
            onChange={set("entry_long")} validation={validating["entry_long"]}
            onBlur={()=>validateField("entry_long",form.entry_long)}
            placeholder="e.g. ma(9) > ma(21)" color="green" />
          <FormulaField label="EXIT LONG" value={form.exit_long}
            onChange={set("exit_long")} validation={validating["exit_long"]}
            onBlur={()=>validateField("exit_long",form.exit_long)}
            placeholder="e.g. ma(9) < ma(21)" color="muted" />
          <FormulaField label="ENTRY SHORT (SELL)" value={form.entry_short}
            onChange={set("entry_short")} validation={validating["entry_short"]}
            onBlur={()=>validateField("entry_short",form.entry_short)}
            placeholder="e.g. ma(9) < ma(21)" color="red" />
          <FormulaField label="EXIT SHORT" value={form.exit_short}
            onChange={set("exit_short")} validation={validating["exit_short"]}
            onBlur={()=>validateField("exit_short",form.exit_short)}
            placeholder="e.g. ma(9) > ma(21)" color="muted" />
        </div>

        {/* Risk settings */}
        <div style={{fontSize:10,letterSpacing:2,color:"var(--green)",margin:"16px 0 8px"}}>RISK PER TRADE</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12}}>
          <FInput label="TARGET %" value={form.target_pct} onChange={set("target_pct")}
            type="number" placeholder="e.g. 2.0" help="Exit at +2% profit" />
          <FInput label="STOP LOSS %" value={form.sl_pct} onChange={set("sl_pct")}
            type="number" placeholder="e.g. 1.0" help="Exit at -1% loss" />
          <div>
            <div className="field">
              <label className="field-label">TRAILING SL</label>
              <div style={{display:"flex",gap:0}}>
                <button type="button" onClick={()=>setForm(f=>({...f,trailing_sl:true}))} style={{
                  flex:1,padding:10,fontFamily:"var(--font)",fontSize:11,cursor:"pointer",
                  borderRight:"none",border:"1px solid",
                  background:form.trailing_sl?"var(--green-dim)":"transparent",
                  borderColor:form.trailing_sl?"rgba(0,255,136,0.4)":"var(--border)",
                  color:form.trailing_sl?"var(--green)":"var(--muted)",
                }}>ON</button>
                <button type="button" onClick={()=>setForm(f=>({...f,trailing_sl:false}))} style={{
                  flex:1,padding:10,fontFamily:"var(--font)",fontSize:11,cursor:"pointer",
                  border:"1px solid",
                  background:!form.trailing_sl?"rgba(74,85,104,0.2)":"transparent",
                  borderColor:"var(--border)",
                  color:!form.trailing_sl?"var(--text)":"var(--muted)",
                }}>OFF</button>
              </div>
            </div>
            {form.trailing_sl && (
              <FInput label="TRAIL %" value={form.trail_pct} onChange={set("trail_pct")}
                type="number" placeholder="e.g. 0.5" help="Trail SL by 0.5% from peak" />
            )}
          </div>
        </div>

        {/* Broker + mode */}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginTop:4}}>
          <div className="field">
            <label className="field-label">BROKER ACCOUNT</label>
            <select className="field-input" value={form.broker_account_id} onChange={set("broker_account_id")}
              style={{background:"rgba(0,255,136,0.04)",color:"var(--text)",fontFamily:"var(--font)"}}>
              <option value="">Select broker</option>
              {brokers.map((b:any)=>(
                <option key={b.id} value={b.id}>
                  {b.broker.toUpperCase()} — {b.paper_trading?"Paper":"Live"}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label">TRADING MODE</label>
            <div style={{display:"flex",gap:0}}>
              <button type="button" onClick={()=>setForm(f=>({...f,paper_trading:true}))} style={{
                flex:1,padding:11,fontFamily:"var(--font)",fontSize:11,cursor:"pointer",
                borderRight:"none",border:"1px solid",
                background:form.paper_trading?"rgba(255,208,96,0.15)":"transparent",
                borderColor:form.paper_trading?"rgba(255,208,96,0.4)":"var(--border)",
                color:form.paper_trading?"var(--yellow)":"var(--muted)",
              }}>◎ PAPER</button>
              <button type="button" onClick={()=>setForm(f=>({...f,paper_trading:false}))} style={{
                flex:1,padding:11,fontFamily:"var(--font)",fontSize:11,cursor:"pointer",
                border:"1px solid",
                background:!form.paper_trading?"rgba(255,68,102,0.1)":"transparent",
                borderColor:!form.paper_trading?"rgba(255,68,102,0.4)":"var(--border)",
                color:!form.paper_trading?"var(--red)":"var(--muted)",
              }}>● LIVE</button>
            </div>
          </div>
        </div>

        <div style={{display:"flex",gap:12,marginTop:16,paddingBottom:8}}>
          <button className={`auth-btn${saveMutation.isPending?" loading":""}`}
            onClick={()=>saveMutation.mutate()} disabled={saveMutation.isPending}
            style={{maxWidth:240}}>
            {saveMutation.isPending?"SAVING...":initial?"UPDATE STRATEGY →":"CREATE STRATEGY →"}
          </button>
          <button className="exit-btn" onClick={onCancel} style={{padding:"12px 20px"}}>CANCEL</button>
        </div>
      </div>
    </div>
  );
}

/* ── POSITIONS TAB ───────────────────────────────────────────────────────── */
function PositionsTab() {
  const qc = useQueryClient();
  const { data: positions, isLoading } = useQuery({
    queryKey: ["managed-positions"],
    queryFn: () => api.get("/formula/positions").then(r=>r.data),
    refetchInterval: 5_000,
  });

  const exitMutation = useMutation({
    mutationFn: ({id,ltp}:{id:string,ltp:number}) =>
      api.post(`/formula/positions/${id}/exit`,{ltp}),
    onSuccess: ()=>{ toast.success("Position closed"); qc.invalidateQueries({queryKey:["managed-positions"]}); },
  });

  const openPositions  = positions?.filter((p:any)=>p.status==="open")  ?? [];
  const closedPositions= positions?.filter((p:any)=>p.status!=="open")  ?? [];

  return (
    <div>
      {/* Open positions */}
      <div className="card" style={{marginBottom:20}}>
        <div className="card-header">
          <span className="card-title">OPEN POSITIONS</span>
          <span className="card-badge">{openPositions.length} open</span>
        </div>
        {openPositions.length===0 ? (
          <div className="empty-state">No open positions. Start a formula strategy to see positions here.</div>
        ) : (
          <table className="data-table">
            <thead><tr>
              {["SYMBOL","DIR","QTY","ENTRY","TARGET","SL","TRAIL","STATUS","ACTION"].map(h=><th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {openPositions.map((p:any)=>(
                <tr key={p.id}>
                  <td className="symbol">{p.symbol}</td>
                  <td><span className={`badge ${p.direction==="BUY"?"badge-green":"badge-red"}`}>{p.direction}</span></td>
                  <td>{p.quantity}</td>
                  <td>₹{p.entry_price?.toLocaleString()}</td>
                  <td style={{color:"var(--green)"}}>{p.target_price?`₹${p.target_price.toLocaleString()}`:"—"}</td>
                  <td style={{color:"var(--red)"}}>{p.sl_price?`₹${p.sl_price.toLocaleString()}`:"—"}</td>
                  <td>{p.trailing_sl?<span className="badge badge-yellow">ON {p.trail_pct}%</span>:"—"}</td>
                  <td><span className="badge badge-green">OPEN</span></td>
                  <td>
                    <button className="exit-btn" onClick={()=>exitMutation.mutate({id:p.id,ltp:p.entry_price})}>
                      EXIT
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Closed positions */}
      {closedPositions.length>0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">CLOSED POSITIONS</span>
            <span className="card-badge">last {closedPositions.length}</span>
          </div>
          <table className="data-table">
            <thead><tr>
              {["SYMBOL","DIR","QTY","ENTRY","EXIT","P&L","REASON","TIME"].map(h=><th key={h}>{h}</th>)}
            </tr></thead>
            <tbody>
              {closedPositions.slice(0,20).map((p:any)=>(
                <tr key={p.id}>
                  <td className="symbol">{p.symbol}</td>
                  <td><span className={`badge ${p.direction==="BUY"?"badge-green":"badge-red"}`}>{p.direction}</span></td>
                  <td>{p.quantity}</td>
                  <td>₹{p.entry_price?.toLocaleString()}</td>
                  <td>₹{p.exit_price?.toLocaleString()}</td>
                  <td className={p.pnl>=0?"pnl-pos":"pnl-neg"}>
                    {p.pnl>=0?"+":""}₹{p.pnl?.toLocaleString()}
                  </td>
                  <td><span className={`badge ${
                    p.exit_reason==="TARGET_HIT"?"badge-green":
                    p.exit_reason==="SL_HIT"?"badge-red":"badge-gray"
                  }`}>{p.exit_reason?.replace("_"," ")}</span></td>
                  <td style={{color:"var(--muted)",fontSize:11}}>
                    {p.closed_at?new Date(p.closed_at).toLocaleTimeString():"—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Small components ────────────────────────────────────────────────────── */
function ConditionChip({label,expr,color}:{label:string,expr:string,color:string}) {
  const c = color==="green"?"var(--green)":color==="red"?"var(--red)":"var(--muted)";
  const bg= color==="green"?"rgba(0,255,136,0.05)":color==="red"?"rgba(255,68,102,0.05)":"rgba(74,85,104,0.1)";
  return (
    <div style={{padding:"10px 12px",background:bg,border:`1px solid ${c}30`}}>
      <div style={{fontSize:9,letterSpacing:2,color:"var(--muted)",marginBottom:4}}>{label}</div>
      <code style={{fontSize:11,color:c}}>{expr}</code>
    </div>
  );
}

function Chip({label,value,color}:{label:string,value:any,color?:string}) {
  const c = color==="green"?"var(--green)":color==="red"?"var(--red)":color==="yellow"?"var(--yellow)":"var(--text)";
  return (
    <div style={{padding:"4px 10px",background:"var(--surface2)",border:"1px solid var(--border)",
      fontSize:11,display:"flex",gap:6,alignItems:"center"}}>
      <span style={{fontSize:9,letterSpacing:1.5,color:"var(--muted)"}}>{label}</span>
      <span style={{fontWeight:700,color:c}}>{value}</span>
    </div>
  );
}

function FInput({label,value,onChange,type="text",placeholder,help}:any) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input className="field-input" type={type} value={value}
        onChange={onChange} placeholder={placeholder} />
      {help&&<div style={{fontSize:10,color:"var(--muted)",marginTop:4}}>{help}</div>}
    </div>
  );
}

function FormulaField({label,value,onChange,onBlur,validation,placeholder,color}:any) {
  const c = color==="green"?"var(--green)":color==="red"?"var(--red)":"var(--muted)";
  const isValid = validation?.startsWith("✓");
  const isError = validation?.startsWith("✗");
  return (
    <div className="field">
      <label className="field-label" style={{color:c}}>{label}</label>
      <input className="field-input" type="text" value={value??""} placeholder={placeholder}
        onChange={onChange} onBlur={onBlur}
        style={isError?{borderColor:"rgba(255,68,102,0.5)"}:isValid?{borderColor:"rgba(0,255,136,0.5)"}:{}} />
      {validation && (
        <div style={{fontSize:10,marginTop:4,color:isValid?"var(--green)":"var(--red)"}}>
          {validation}
        </div>
      )}
    </div>
  );
}
