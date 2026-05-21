import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createChart, ColorType } from "lightweight-charts";
import Layout from "@/components/common/Layout";
import TickerBar from "@/components/common/TickerBar";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

const TIMEFRAMES = [
  { label:"1m",value:"1" },{ label:"5m",value:"5" },
  { label:"15m",value:"15" },{ label:"30m",value:"30" },{ label:"1h",value:"60" },
];
const INDICATORS = ["MA9","MA21","MA50","Volume","BB"];

const DEFAULT_WATCHLIST = ["RELIANCE","TCS","INFY","HDFCBANK","NIFTY50","BANKNIFTY"];

export default function ChartsPage() {
  const [symbol,     setSymbol]     = useState("RELIANCE");
  const [timeframe,  setTimeframe]  = useState("5");
  const [indicators, setIndicators] = useState<string[]>(["MA9","MA21","Volume"]);
  const [tab,        setTab]        = useState<"chart"|"backtest"|"signals">("chart");
  const [watchlist,  setWatchlist]  = useState<string[]>(DEFAULT_WATCHLIST);
  const [alerts,     setAlerts]     = useState<any[]>([]);
  const [showAlertForm, setShowAlertForm] = useState(false);

  return (
    <Layout>
      {/* Ticker strip */}
      <TickerBar onSelect={setSymbol} />

      <div style={{ padding:"12px 0 0" }}>
        {/* Top toolbar */}
        <div style={{ display:"flex", gap:8, marginBottom:12, flexWrap:"wrap", alignItems:"center" }}>
          <div className="tab-switcher">
            <button className={`tab-btn${tab==="chart"    ?" active":""}`} onClick={()=>setTab("chart")}>📈 CHART</button>
            <button className={`tab-btn${tab==="backtest" ?" active":""}`} onClick={()=>setTab("backtest")}>⚡ BACKTEST</button>
            <button className={`tab-btn${tab==="signals"  ?" active":""}`} onClick={()=>setTab("signals")}>📡 SIGNALS</button>
          </div>

          <div style={{ width:1, height:24, background:"var(--border)" }} />

          {/* Timeframes */}
          <div style={{ display:"flex" }}>
            {TIMEFRAMES.map((tf,i)=>(
              <button key={tf.value} onClick={()=>setTimeframe(tf.value)} style={{
                padding:"6px 12px", fontSize:11, fontFamily:"var(--font)", cursor:"pointer",
                background: timeframe===tf.value?"var(--green-dim)":"transparent",
                border:`1px solid ${timeframe===tf.value?"rgba(0,255,136,0.4)":"var(--border)"}`,
                borderRight: i<TIMEFRAMES.length-1?"none":undefined,
                color: timeframe===tf.value?"var(--green)":"var(--muted)",
                transition:"all 0.15s",
              }}>{tf.label}</button>
            ))}
          </div>

          <div style={{ width:1, height:24, background:"var(--border)" }} />

          {/* Indicators */}
          <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
            {INDICATORS.map(ind=>(
              <button key={ind} onClick={()=>setIndicators(prev=>
                prev.includes(ind)?prev.filter(i=>i!==ind):[...prev,ind]
              )} style={{
                padding:"5px 10px", fontSize:10, fontFamily:"var(--font)", cursor:"pointer",
                background: indicators.includes(ind)?"rgba(88,166,255,0.1)":"transparent",
                border:`1px solid ${indicators.includes(ind)?"rgba(88,166,255,0.4)":"var(--border)"}`,
                color: indicators.includes(ind)?"#58a6ff":"var(--muted)",
                transition:"all 0.15s",
              }}>{ind}</button>
            ))}
          </div>
        </div>

        {/* Main chart layout */}
        <div className="chart-layout">
          {/* Left: Watchlist */}
          <div className="chart-sidebar-left">
            <div style={{ padding:"10px 12px", borderBottom:"1px solid var(--border)",
              fontSize:10, letterSpacing:2, color:"var(--muted)" }}>WATCHLIST</div>
            <WatchlistPanel
              watchlist={watchlist}
              selected={symbol}
              onSelect={setSymbol}
              onAdd={(s)=>!watchlist.includes(s)&&setWatchlist(w=>[...w,s])}
              onRemove={(s)=>setWatchlist(w=>w.filter(x=>x!==s))}
            />
          </div>

          {/* Center: Chart */}
          <div className="chart-main">
            {tab==="chart"    && <CandleChart symbol={symbol} timeframe={timeframe}
              indicators={indicators} alerts={alerts} />}
            {tab==="backtest" && <BacktestPanel symbol={symbol} timeframe={parseInt(timeframe)} />}
            {tab==="signals"  && <ManualSignals symbol={symbol} />}
          </div>

          {/* Right: Alerts + Quote */}
          <div className="chart-sidebar-right">
            <QuotePanel symbol={symbol} />
            <AlertsPanel
              symbol={symbol}
              alerts={alerts}
              onAdd={(a)=>setAlerts(prev=>[...prev,a])}
              onRemove={(i)=>setAlerts(prev=>prev.filter((_,idx)=>idx!==i))}
              showForm={showAlertForm}
              setShowForm={setShowAlertForm}
            />
          </div>
        </div>
      </div>
    </Layout>
  );
}

/* ── WATCHLIST ────────────────────────────────────────────── */
function WatchlistPanel({ watchlist, selected, onSelect, onAdd, onRemove }: any) {
  const [search, setSearch] = useState("");
  const { data: instruments } = useQuery({
    queryKey:["instruments", search],
    queryFn:()=>api.get(`/market/instruments?q=${search}`).then(r=>r.data),
    enabled: search.length > 0,
  });

  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column" }}>
      <div style={{ padding:"8px 10px", borderBottom:"1px solid var(--border)" }}>
        <input
          style={{ width:"100%", background:"rgba(0,255,136,0.04)",
            border:"1px solid var(--border)", color:"var(--text)",
            padding:"6px 8px", fontSize:11, fontFamily:"var(--font)", outline:"none" }}
          placeholder="Search symbol..."
          value={search} onChange={e=>setSearch(e.target.value.toUpperCase())}
        />
        {search && instruments?.map((inst:any)=>(
          <div key={inst.symbol} onClick={()=>{ onAdd(inst.symbol); setSearch(""); }}
            style={{ padding:"6px 8px", fontSize:11, cursor:"pointer",
              color:"var(--text)", borderBottom:"1px solid var(--border)" }}>
            <span style={{fontWeight:600}}>{inst.symbol}</span>
            <span style={{color:"var(--muted)",marginLeft:6,fontSize:10}}>{inst.name}</span>
          </div>
        ))}
      </div>
      {watchlist.map((sym:string)=>(
        <WatchlistRow key={sym} symbol={sym} selected={selected===sym}
          onSelect={()=>onSelect(sym)} onRemove={()=>onRemove(sym)} />
      ))}
    </div>
  );
}

function WatchlistRow({ symbol, selected, onSelect, onRemove }: any) {
  const { data:quote } = useQuery({
    queryKey:["quote",symbol],
    queryFn:()=>api.get(`/market/quote/${symbol}`).then(r=>r.data),
    refetchInterval:10_000,
  });
  return (
    <div className={`watchlist-item${selected?" active":""}`} onClick={onSelect}>
      <div>
        <div style={{fontSize:12,fontWeight:600,color:"var(--text)"}}>{symbol}</div>
        <div style={{fontSize:10,color:"var(--muted)"}}>NSE</div>
      </div>
      <div style={{textAlign:"right"}}>
        <div style={{fontSize:12}}>₹{quote?.ltp?.toLocaleString()??"-"}</div>
        <div style={{fontSize:10,color:quote?.change_pct>=0?"var(--green)":"var(--red)"}}>
          {quote?`${quote.change_pct>=0?"+":""}${quote.change_pct}%`:""}
        </div>
      </div>
    </div>
  );
}

/* ── QUOTE PANEL ─────────────────────────────────────────── */
function QuotePanel({ symbol }: { symbol:string }) {
  const { data:q } = useQuery({
    queryKey:["quote",symbol],
    queryFn:()=>api.get(`/market/quote/${symbol}`).then(r=>r.data),
    refetchInterval:5_000,
  });
  if (!q) return <div style={{padding:16,color:"var(--muted)",fontSize:11}}>Loading...</div>;

  return (
    <div style={{padding:16,borderBottom:"1px solid var(--border)"}}>
      <div style={{fontSize:13,fontWeight:700,marginBottom:4}}>{symbol}</div>
      <div style={{fontSize:22,fontWeight:700,marginBottom:4}}>₹{q.ltp?.toLocaleString()}</div>
      <div style={{fontSize:12,color:q.change_pct>=0?"var(--green)":"var(--red)",marginBottom:12}}>
        {q.change_pct>=0?"▲":"▼"} ₹{Math.abs(q.change).toFixed(2)} ({Math.abs(q.change_pct).toFixed(2)}%)
      </div>
      {[
        ["OPEN",   `₹${q.open?.toLocaleString()}`],
        ["HIGH",   `₹${q.high?.toLocaleString()}`],
        ["LOW",    `₹${q.low?.toLocaleString()}`],
        ["VOLUME", `${(q.volume/100000).toFixed(1)}L`],
        ["52W H",  `₹${q["52w_high"]?.toLocaleString()}`],
        ["52W L",  `₹${q["52w_low"]?.toLocaleString()}`],
      ].map(([l,v])=>(
        <div key={l} style={{display:"flex",justifyContent:"space-between",
          padding:"4px 0",borderBottom:"1px solid rgba(255,255,255,0.03)"}}>
          <span style={{fontSize:10,color:"var(--muted)",letterSpacing:1}}>{l}</span>
          <span style={{fontSize:11}}>{v}</span>
        </div>
      ))}
    </div>
  );
}

/* ── ALERTS PANEL ────────────────────────────────────────── */
function AlertsPanel({ symbol, alerts, onAdd, onRemove, showForm, setShowForm }: any) {
  const [price, setPrice] = useState("");
  const [condition, setCondition] = useState<"above"|"below">("above");

  function addAlert() {
    if (!price) return;
    onAdd({ symbol, price:parseFloat(price), condition, triggered:false });
    setPrice("");
    setShowForm(false);
    toast.success(`Alert set: ${symbol} ${condition} ₹${price}`);
  }

  const symbolAlerts = alerts.filter((a:any)=>a.symbol===symbol);

  return (
    <div style={{padding:16}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <span style={{fontSize:10,letterSpacing:2,color:"var(--muted)"}}>PRICE ALERTS</span>
        <button className="connect-btn" style={{padding:"4px 10px",fontSize:10}}
          onClick={()=>setShowForm((v:boolean)=>!v)}>
          {showForm?"✕":"+ ALERT"}
        </button>
      </div>

      {showForm && (
        <div style={{marginBottom:12}}>
          <div style={{display:"flex",gap:0,marginBottom:8}}>
            {(["above","below"] as const).map(c=>(
              <button key={c} onClick={()=>setCondition(c)} style={{
                flex:1, padding:"7px 0", fontSize:10, fontFamily:"var(--font)", cursor:"pointer",
                borderRight:c==="above"?"none":undefined,
                border:"1px solid",
                background:condition===c?c==="above"?"rgba(0,255,136,0.15)":"rgba(255,68,102,0.1)":"transparent",
                borderColor:condition===c?c==="above"?"rgba(0,255,136,0.4)":"rgba(255,68,102,0.4)":"var(--border)",
                color:condition===c?c==="above"?"var(--green)":"var(--red)":"var(--muted)",
                letterSpacing:1,
              }}>{c.toUpperCase()}</button>
            ))}
          </div>
          <input style={{ width:"100%", background:"rgba(0,255,136,0.04)",
            border:"1px solid var(--border)", color:"var(--text)",
            padding:"8px 10px", fontSize:12, fontFamily:"var(--font)",
            outline:"none", marginBottom:8, boxSizing:"border-box" }}
            type="number" placeholder="Target price ₹" value={price}
            onChange={e=>setPrice(e.target.value)}
            onKeyDown={e=>e.key==="Enter"&&addAlert()} />
          <button onClick={addAlert} style={{
            width:"100%", padding:"8px", background:"var(--green-dim)",
            border:"1px solid rgba(0,255,136,0.3)", color:"var(--green)",
            fontFamily:"var(--font)", fontSize:11, cursor:"pointer", letterSpacing:1,
          }}>SET ALERT</button>
        </div>
      )}

      {symbolAlerts.length===0 && (
        <div style={{fontSize:11,color:"var(--muted)",textAlign:"center",padding:"16px 0"}}>
          No alerts for {symbol}
        </div>
      )}

      {symbolAlerts.map((a:any,i:number)=>(
        <div key={i} style={{
          display:"flex",justifyContent:"space-between",alignItems:"center",
          padding:"8px 0",borderBottom:"1px solid var(--border)",
        }}>
          <div>
            <div style={{fontSize:11}}>
              <span style={{color:a.condition==="above"?"var(--green)":"var(--red)"}}>
                {a.condition==="above"?"▲ Above":"▼ Below"}
              </span>
              {" "}₹{a.price.toLocaleString()}
            </div>
            {a.triggered && <div style={{fontSize:9,color:"var(--yellow)"}}>● TRIGGERED</div>}
          </div>
          <button onClick={()=>onRemove(alerts.indexOf(a))} style={{
            background:"transparent",border:"none",color:"var(--muted)",
            cursor:"pointer",fontSize:14,padding:"2px 6px",
          }}>×</button>
        </div>
      ))}
    </div>
  );
}

/* ── CANDLESTICK CHART ───────────────────────────────────── */
function CandleChart({ symbol, timeframe, indicators, alerts }: any) {
  const chartRef  = useRef<HTMLDivElement>(null);
  const chartObj  = useRef<any>(null);
  const seriesRef = useRef<any>({});

  const { data, isLoading } = useQuery({
    queryKey:["candles",symbol,timeframe],
    queryFn:()=>api.get(`/market/candles?symbol=${symbol}&timeframe=${timeframe}&bars=300`).then(r=>r.data),
    refetchInterval:30_000,
  });

  useEffect(()=>{
    if(!chartRef.current) return;
    const chart = createChart(chartRef.current,{
      layout:{ background:{type:ColorType.Solid,color:"#0d1117"}, textColor:"#4a5568" },
      grid:{ vertLines:{color:"rgba(255,255,255,0.03)"}, horzLines:{color:"rgba(255,255,255,0.03)"} },
      crosshair:{mode:1},
      rightPriceScale:{borderColor:"#30363d"},
      timeScale:{borderColor:"#30363d",timeVisible:true},
      width:chartRef.current.clientWidth,
      height:chartRef.current.clientHeight||460,
    });
    chartObj.current = chart;

    seriesRef.current.candles = chart.addCandlestickSeries({
      upColor:"#00ff88",downColor:"#ff4466",
      borderUpColor:"#00ff88",borderDownColor:"#ff4466",
      wickUpColor:"#00ff88",wickDownColor:"#ff4466",
    });
    seriesRef.current.volume = chart.addHistogramSeries({
      color:"rgba(0,255,136,0.3)",priceFormat:{type:"volume"},priceScaleId:"volume",
    });
    chart.priceScale("volume").applyOptions({scaleMargins:{top:0.8,bottom:0}});

    seriesRef.current.ma9  = chart.addLineSeries({color:"#58a6ff",lineWidth:1,priceLineVisible:false});
    seriesRef.current.ma21 = chart.addLineSeries({color:"#ffd060",lineWidth:1,priceLineVisible:false});
    seriesRef.current.ma50 = chart.addLineSeries({color:"#ff6b9d",lineWidth:1,priceLineVisible:false});
    seriesRef.current.bbUpper = chart.addLineSeries({color:"rgba(88,166,255,0.4)",lineWidth:1,priceLineVisible:false,lineStyle:2});
    seriesRef.current.bbLower = chart.addLineSeries({color:"rgba(88,166,255,0.4)",lineWidth:1,priceLineVisible:false,lineStyle:2});

    const ro = new ResizeObserver(()=>{
      if(chartRef.current) chart.applyOptions({width:chartRef.current.clientWidth,height:chartRef.current.clientHeight||460});
    });
    ro.observe(chartRef.current);
    return ()=>{ ro.disconnect(); chart.remove(); };
  },[]);

  useEffect(()=>{
    if(!data?.candles||!chartObj.current) return;
    const c = data.candles;
    seriesRef.current.candles?.setData(c.map((x:any)=>({time:x.time,open:x.open,high:x.high,low:x.low,close:x.close})));
    seriesRef.current.volume?.setData(c.map((x:any)=>({time:x.time,value:x.volume,color:x.close>=x.open?"rgba(0,255,136,0.3)":"rgba(255,68,102,0.3)"})));
    const closes=c.map((x:any)=>x.close), times=c.map((x:any)=>x.time);
    seriesRef.current.ma9?.setData(_ma(closes,times,9));
    seriesRef.current.ma21?.setData(_ma(closes,times,21));
    seriesRef.current.ma50?.setData(_ma(closes,times,50));
    // Bollinger Bands (20,2)
    const bb = _bb(closes,times,20,2);
    seriesRef.current.bbUpper?.setData(bb.upper);
    seriesRef.current.bbLower?.setData(bb.lower);
    chartObj.current.timeScale().fitContent();
  },[data]);

  useEffect(()=>{
    if(!chartObj.current) return;
    seriesRef.current.ma9?.applyOptions({visible:indicators.includes("MA9")});
    seriesRef.current.ma21?.applyOptions({visible:indicators.includes("MA21")});
    seriesRef.current.ma50?.applyOptions({visible:indicators.includes("MA50")});
    seriesRef.current.volume?.applyOptions({visible:indicators.includes("Volume")});
    seriesRef.current.bbUpper?.applyOptions({visible:indicators.includes("BB")});
    seriesRef.current.bbLower?.applyOptions({visible:indicators.includes("BB")});
  },[indicators]);

  return (
    <div style={{flex:1,display:"flex",flexDirection:"column",background:"#0d1117",position:"relative"}}>
      {/* Quote bar */}
      <QuoteBar symbol={symbol} />
      {isLoading&&<div style={{position:"absolute",inset:0,display:"flex",alignItems:"center",
        justifyContent:"center",color:"var(--muted)",fontSize:12,zIndex:1}}>Loading…</div>}
      <div ref={chartRef} style={{flex:1,width:"100%"}} />
    </div>
  );
}

function QuoteBar({ symbol }: { symbol:string }) {
  const { data:q } = useQuery({
    queryKey:["quote",symbol],
    queryFn:()=>api.get(`/market/quote/${symbol}`).then(r=>r.data),
    refetchInterval:5_000,
  });
  return (
    <div style={{display:"flex",gap:16,alignItems:"center",padding:"8px 16px",
      borderBottom:"1px solid var(--border)",background:"#0d1117",flexWrap:"wrap"}}>
      <span style={{fontWeight:700,fontSize:13}}>{symbol}</span>
      {q&&<>
        <span style={{fontSize:16,fontWeight:700}}>₹{q.ltp?.toLocaleString()}</span>
        <span style={{fontSize:12,color:q.change_pct>=0?"var(--green)":"var(--red)"}}>
          {q.change_pct>=0?"▲":"▼"} {Math.abs(q.change_pct).toFixed(2)}%
        </span>
        <span style={{fontSize:11,color:"var(--muted)"}}>O:{q.open} H:{q.high} L:{q.low}</span>
        <span style={{fontSize:11,color:"var(--muted)",marginLeft:"auto"}}>Vol:{(q.volume/100000).toFixed(1)}L</span>
      </>}
    </div>
  );
}

/* ── BACKTEST ─────────────────────────────────────────────── */
function BacktestPanel({ symbol, timeframe }: { symbol:string; timeframe:number }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [params,setParams]=useState({fast:9,slow:21,quantity:1});
  const [result,setResult]=useState<any>(null);
  const [loading,setLoading]=useState(false);
  const set=(k:string)=>(e:any)=>setParams(p=>({...p,[k]:parseInt(e.target.value)}));

  async function run() {
    setLoading(true);
    try {
      const r=await api.post("/backtest/run",{engine_class:"moving_average_crossover",
        symbol,timeframe_minutes:timeframe,bars:500,initial_capital:100000,params});
      setResult(r.data);
    } catch(e){console.error(e);} finally{setLoading(false);}
  }

  useEffect(()=>{
    if(!result?.equity_curve?.length||!chartRef.current) return;
    chartRef.current.innerHTML="";
    const chart=createChart(chartRef.current,{
      layout:{background:{type:ColorType.Solid,color:"#0d1117"},textColor:"#4a5568"},
      grid:{vertLines:{color:"rgba(255,255,255,0.03)"},horzLines:{color:"rgba(255,255,255,0.03)"}},
      rightPriceScale:{borderColor:"#30363d"},timeScale:{borderColor:"#30363d",timeVisible:true},
      width:chartRef.current.clientWidth,height:220,
    });
    const s=chart.addLineSeries({color:"#00ff88",lineWidth:2,priceLineVisible:false});
    s.setData(result.equity_curve.map((p:any)=>({time:p.time,value:p.equity})));
    chart.timeScale().fitContent();
    const ro=new ResizeObserver(()=>{if(chartRef.current)chart.applyOptions({width:chartRef.current.clientWidth});});
    ro.observe(chartRef.current);
    return()=>{ro.disconnect();chart.remove();};
  },[result]);

  return (
    <div style={{flex:1,overflow:"auto",padding:16}}>
      <div className="card" style={{marginBottom:12}}>
        <div className="card-header"><span className="card-title">BACKTEST — {symbol} · {timeframe}m</span></div>
        <div style={{padding:"16px",display:"grid",gridTemplateColumns:"1fr 1fr 1fr auto",gap:12,alignItems:"end"}}>
          <RInput label="FAST MA"  value={params.fast}     onChange={set("fast")} />
          <RInput label="SLOW MA"  value={params.slow}     onChange={set("slow")} />
          <RInput label="QTY"      value={params.quantity}  onChange={set("quantity")} />
          <button className={`auth-btn${loading?" loading":""}`} onClick={run}
            disabled={loading} style={{height:42,whiteSpace:"nowrap"}}>
            {loading?"RUNNING…":"▶ RUN"}
          </button>
        </div>
      </div>

      {result&&<>
        <div className="stats-grid" style={{gridTemplateColumns:"repeat(3,1fr)",marginBottom:12}}>
          <BtStat label="TRADES"   value={result.total_trades} />
          <BtStat label="WIN RATE" value={`${result.win_rate}%`} pos={result.win_rate>=50} neg={result.win_rate<50} />
          <BtStat label="NET P&L"  value={`₹${result.total_pnl.toLocaleString()}`} pos={result.total_pnl>=0} neg={result.total_pnl<0} />
          <BtStat label="DRAWDOWN" value={`${result.max_drawdown}%`} neg={result.max_drawdown>15} />
          <BtStat label="SHARPE"   value={result.sharpe_ratio} pos={result.sharpe_ratio>=1} neg={result.sharpe_ratio<0} />
          <BtStat label="W/L"      value={`${result.winning_trades}/${result.losing_trades}`} />
        </div>
        <div className="card" style={{marginBottom:12}}>
          <div className="card-header"><span className="card-title">EQUITY CURVE</span></div>
          <div ref={chartRef} style={{width:"100%"}} />
        </div>
        <div className="card">
          <div className="card-header">
            <span className="card-title">TRADE LOG</span>
            <span className="card-badge">{result.trades.length} trades</span>
          </div>
          <table className="data-table">
            <thead><tr>{["ENTRY","EXIT","ENTRY ₹","EXIT ₹","P&L","RESULT"].map(h=><th key={h}>{h}</th>)}</tr></thead>
            <tbody>{result.trades.map((t:any,i:number)=>(
              <tr key={i}>
                <td style={{color:"var(--muted)",fontSize:10}}>{t.entry_time?.split(".")[0]}</td>
                <td style={{color:"var(--muted)",fontSize:10}}>{t.exit_time?.split(".")[0]}</td>
                <td>₹{t.entry_price?.toLocaleString()}</td>
                <td>₹{t.exit_price?.toLocaleString()}</td>
                <td className={t.pnl>=0?"pnl-pos":"pnl-neg"}>{t.pnl>=0?"+":""}₹{t.pnl?.toLocaleString()}</td>
                <td><span className={`badge ${t.pnl>=0?"badge-green":"badge-red"}`}>{t.pnl>=0?"WIN":"LOSS"}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </>}
    </div>
  );
}

/* ── MANUAL SIGNALS ───────────────────────────────────────── */
function ManualSignals({ symbol }: { symbol:string }) {
  const [form,setForm]=useState({symbol,direction:"BUY",quantity:"",price:"",strategy_tag:"MANUAL"});
  const [sent,setSent]=useState(false);
  const [loading,setLoading]=useState(false);
  const set=(k:string)=>(e:any)=>setForm(f=>({...f,[k]:e.target.value}));
  useEffect(()=>setForm(f=>({...f,symbol})),[symbol]);

  async function send(){
    setLoading(true);
    try{
      await api.post("/signals/manual",{
        symbol:form.symbol, exchange:"NSE", direction:form.direction,
        quantity:form.quantity?parseInt(form.quantity):null,
        price:form.price?parseFloat(form.price):null,
        strategy_tag:form.strategy_tag||"MANUAL",
      });
      setSent(true); toast.success("Signal sent to all followers!");
      setTimeout(()=>setSent(false),3000);
    }catch(e){console.error(e);}finally{setLoading(false);}
  }

  const {data:history}=useQuery({
    queryKey:["signal-history"],
    queryFn:()=>api.get("/signals/history?limit=20").then(r=>r.data),
    refetchInterval:10_000,
  });

  return (
    <div style={{flex:1,overflow:"auto",padding:16,display:"grid",gridTemplateColumns:"340px 1fr",gap:16}}>
      <div className="card">
        <div className="card-header"><span className="card-title">MANUAL SIGNAL</span></div>
        <div style={{padding:"16px 16px 8px"}}>
          <div className="field">
            <label className="field-label">SYMBOL</label>
            <input className="field-input" value={form.symbol} onChange={set("symbol")} />
          </div>
          <div className="field">
            <label className="field-label">DIRECTION</label>
            <div style={{display:"flex"}}>
              {["BUY","SELL","EXIT"].map((d,i)=>(
                <button key={d} type="button" onClick={()=>setForm(f=>({...f,direction:d}))} style={{
                  flex:1, padding:10, fontFamily:"var(--font)", fontSize:11,
                  letterSpacing:1, cursor:"pointer", borderRight:i<2?"none":undefined, border:"1px solid",
                  background:form.direction===d?d==="BUY"?"rgba(0,255,136,0.15)":d==="SELL"?"rgba(255,68,102,0.1)":"rgba(255,208,96,0.1)":"transparent",
                  borderColor:form.direction===d?d==="BUY"?"rgba(0,255,136,0.4)":d==="SELL"?"rgba(255,68,102,0.4)":"rgba(255,208,96,0.4)":"var(--border)",
                  color:form.direction===d?d==="BUY"?"var(--green)":d==="SELL"?"var(--red)":"var(--yellow)":"var(--muted)",
                }}>{d}</button>
              ))}
            </div>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
            <div className="field"><label className="field-label">QTY</label>
              <input className="field-input" type="number" value={form.quantity} onChange={set("quantity")} placeholder="1" /></div>
            <div className="field"><label className="field-label">PRICE</label>
              <input className="field-input" type="number" value={form.price} onChange={set("price")} placeholder="Market" /></div>
          </div>
          <div className="field"><label className="field-label">TAG</label>
            <input className="field-input" value={form.strategy_tag} onChange={set("strategy_tag")} /></div>
          <button className={`auth-btn${loading?" loading":""}`} onClick={send}
            disabled={loading||!form.symbol}
            style={{marginTop:4,
              background:sent?"var(--green)":form.direction==="SELL"?"rgba(255,68,102,0.85)":form.direction==="EXIT"?"rgba(255,208,96,0.85)":undefined,
              color:sent||(form.direction!=="BUY")?"var(--bg)":undefined,
            }}>
            {sent?"✓ SENT!":loading?"SENDING…":`SEND ${form.direction} →`}
          </button>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">SIGNAL HISTORY</span>
          <span className="card-badge">{history?.length??0}</span>
        </div>
        {!history?.length?<div className="empty-state">No signals yet.</div>:(
          <table className="data-table">
            <thead><tr>{["TIME","SYMBOL","DIR","QTY","TAG","STATUS"].map(h=><th key={h}>{h}</th>)}</tr></thead>
            <tbody>{history.map((s:any)=>(
              <tr key={s.id}>
                <td style={{color:"var(--muted)",fontSize:10}}>{new Date(s.created_at).toLocaleTimeString()}</td>
                <td className="symbol">{s.symbol}</td>
                <td><span className={`badge ${s.direction==="BUY"?"badge-green":"badge-red"}`}>{s.direction}</span></td>
                <td>{s.quantity??"-"}</td>
                <td style={{color:"var(--muted)",fontSize:10}}>{s.strategy_tag}</td>
                <td><span className={`badge ${s.status==="done"?"badge-green":s.status==="failed"?"badge-red":"badge-yellow"}`}>{s.status?.toUpperCase()}</span></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ── Helpers ──────────────────────────────────────────────── */
function _ma(closes:number[],times:number[],p:number){
  return closes.slice(p-1).map((_,i)=>({
    time:times[i+p-1],
    value:Math.round(closes.slice(i,i+p).reduce((a,b)=>a+b,0)/p*100)/100
  }));
}
function _bb(closes:number[],times:number[],p:number,std:number){
  const upper=[],lower=[];
  for(let i=p-1;i<closes.length;i++){
    const slice=closes.slice(i-p+1,i+1);
    const mean=slice.reduce((a,b)=>a+b,0)/p;
    const variance=slice.reduce((a,b)=>a+(b-mean)**2,0)/p;
    const sd=Math.sqrt(variance);
    upper.push({time:times[i],value:Math.round((mean+std*sd)*100)/100});
    lower.push({time:times[i],value:Math.round((mean-std*sd)*100)/100});
  }
  return{upper,lower};
}
function BtStat({label,value,pos,neg}:any){
  return(<div className="stat-card">
    <div className="stat-label">{label}</div>
    <div className="stat-value" style={{color:pos?"var(--green)":neg?"var(--red)":"var(--text)"}}>{value}</div>
  </div>);
}
function RInput({label,value,onChange}:any){
  return(<div className="field">
    <label className="field-label">{label}</label>
    <input className="field-input" type="number" value={value} onChange={onChange}/>
  </div>);
}
