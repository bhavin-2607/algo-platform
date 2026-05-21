import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createChart, ColorType } from "lightweight-charts";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

export default function MarketPage() {
  const [selected,   setSelected]   = useState("NIFTY50");
  const [quotesMap,  setQuotesMap]  = useState<Record<string,any>>({});
  const [wsStatus,   setWsStatus]   = useState<"connecting"|"live"|"polling">("connecting");
  const [lastUpdate, setLastUpdate] = useState<Date|null>(null);
  const [showAdd,    setShowAdd]    = useState(false);
  const { accessToken } = useAuthStore();
  const wsRef = useRef<WebSocket|null>(null);
  const qc    = useQueryClient();

  // Watchlist from server
  const { data: wlData } = useQuery({
    queryKey: ["watchlist"],
    queryFn:  () => api.get("/market/watchlist").then(r => r.data.symbols as string[]),
  });
  const watchlist: string[] = wlData ?? ["NIFTY50","BANKNIFTY","RELIANCE","TCS","INFY",
    "HDFCBANK","ICICIBANK","SBIN","WIPRO","TATAMOTORS","BAJFINANCE"];

  const removeMutation = useMutation({
    mutationFn: (sym: string) => api.delete(`/market/watchlist/${sym}`),
    onSuccess:  () => { toast.success("Removed"); qc.invalidateQueries({queryKey:["watchlist"]}); },
  });

  // WebSocket live feed
  useEffect(() => {
    if (!accessToken || watchlist.length === 0) return;
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
            setQuotesMap(prev => {
              const next = {...prev};
              msg.data.forEach((q:any) => { next[q.symbol] = q; });
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
    return () => { wsRef.current?.close(); };
  }, [accessToken]); // reconnect only on auth change

  // REST fallback
  useQuery({
    queryKey: ["live-quotes-fallback"],
    queryFn: async () => {
      const data = await api.get(`/market/live-quotes?symbols=${watchlist.join(",")}`).then(r=>r.data);
      if (wsStatus !== "live") {
        const map: Record<string,any> = {};
        data.forEach((q:any) => { map[q.symbol] = q; });
        setQuotesMap(map);
        setLastUpdate(new Date());
      }
      return data;
    },
    refetchInterval: 4_000,
    enabled: wsStatus !== "live",
  });

  const selectedQuote = quotesMap[selected];
  const isLive        = wsStatus === "live";

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">LIVE MARKET</h1>
          <p className="page-sub" style={{display:"flex",alignItems:"center",gap:12}}>
            <span style={{display:"flex",alignItems:"center",gap:6,
              color:isLive?"var(--green)":wsStatus==="connecting"?"var(--yellow)":"var(--muted)"}}>
              <span style={{width:7,height:7,borderRadius:"50%",display:"inline-block",
                background:isLive?"var(--green)":wsStatus==="connecting"?"var(--yellow)":"var(--muted)",
                boxShadow:isLive?"0 0 6px var(--green)":"none"}} />
              {isLive?"LIVE — 4s WebSocket":wsStatus==="connecting"?"CONNECTING...":"POLLING — 4s REST"}
            </span>
            {lastUpdate && <span style={{fontSize:10,color:"var(--muted)"}}>
              {lastUpdate.toLocaleTimeString()}
            </span>}
          </p>
        </div>
        <button className="connect-btn" onClick={()=>setShowAdd(v=>!v)}>
          {showAdd ? "✕ CLOSE" : "+ ADD SYMBOL"}
        </button>
      </div>

      {showAdd && <AddSymbolPanel onAdded={()=>{
        qc.invalidateQueries({queryKey:["watchlist"]});
        setShowAdd(false);
      }} />}

      <div style={{display:"grid",gridTemplateColumns:"280px 1fr",gap:16}}>

        {/* Watchlist */}
        <div className="card" style={{height:"fit-content"}}>
          <div className="card-header">
            <span className="card-title">WATCHLIST</span>
            <span className="card-badge">{watchlist.length}</span>
          </div>
          <div style={{padding:"8px 0"}}>
            {watchlist.map(sym => {
              const q   = quotesMap[sym];
              const pos = (q?.change_pct ?? 0) >= 0;
              return (
                <div key={sym} style={{
                  display:"flex",alignItems:"center",
                  background:selected===sym?"var(--green-dim)":"transparent",
                  borderLeft:selected===sym?"2px solid var(--green)":"2px solid transparent",
                }}>
                  <div onClick={()=>setSelected(sym)} style={{
                    flex:1,padding:"10px 12px",cursor:"pointer",
                    display:"flex",justifyContent:"space-between",alignItems:"center",
                  }}>
                    <div>
                      <div style={{fontSize:12,fontWeight:700,
                        color:selected===sym?"var(--green)":"var(--text)"}}>{sym}</div>
                      {q && <div style={{fontSize:10,color:"var(--muted)"}}>
                        {q.volume?(q.volume/100000).toFixed(1)+"L":"—"}
                      </div>}
                    </div>
                    <div style={{textAlign:"right"}}>
                      <div style={{fontSize:13,fontWeight:700}}>
                        {q?`₹${Number(q.ltp).toLocaleString()}`:"—"}
                      </div>
                      {q && <div style={{fontSize:10,fontWeight:600,
                        color:pos?"var(--green)":"var(--red)"}}>
                        {pos?"▲":"▼"} {Math.abs(q.change_pct).toFixed(2)}%
                      </div>}
                    </div>
                  </div>
                  <button onClick={()=>removeMutation.mutate(sym)}
                    style={{padding:"4px 8px",marginRight:6,background:"transparent",
                      border:"none",color:"var(--muted)",cursor:"pointer",fontSize:12,
                      opacity:0.4}}
                    title="Remove">✕</button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Detail panel */}
        <div>
          <div className="card" style={{marginBottom:16}}>
            <div style={{padding:"20px 24px",display:"flex",gap:32,
              alignItems:"center",flexWrap:"wrap",
              borderBottom:"1px solid var(--border)"}}>
              <div>
                <div style={{fontSize:22,fontWeight:700,letterSpacing:1}}>{selected}</div>
                <div style={{fontSize:11,color:"var(--muted)"}}>NSE · EQUITY</div>
              </div>
              {selectedQuote ? <>
                <div>
                  <div style={{fontSize:36,fontWeight:700,letterSpacing:-1}}>
                    ₹{Number(selectedQuote.ltp).toLocaleString()}
                  </div>
                  <div style={{fontSize:14,fontWeight:600,
                    color:selectedQuote.change_pct>=0?"var(--green)":"var(--red)"}}>
                    {selectedQuote.change_pct>=0?"▲":"▼"}{" "}
                    ₹{Math.abs(selectedQuote.change).toFixed(2)}{" "}
                    ({Math.abs(selectedQuote.change_pct).toFixed(2)}%)
                  </div>
                </div>
                <div style={{display:"flex",gap:24,flexWrap:"wrap"}}>
                  {[["OPEN",selectedQuote.open],["HIGH",selectedQuote.high],
                    ["LOW",selectedQuote.low],["CLOSE",selectedQuote.close]].map(([l,v])=>(
                    <div key={l as string}>
                      <div style={{fontSize:9,letterSpacing:2,color:"var(--muted)",marginBottom:2}}>{l}</div>
                      <div style={{fontSize:13,fontWeight:600,
                        color:l==="HIGH"?"var(--green)":l==="LOW"?"var(--red)":"var(--text)"}}>
                        ₹{Number(v).toLocaleString()}
                      </div>
                    </div>
                  ))}
                  <div>
                    <div style={{fontSize:9,letterSpacing:2,color:"var(--muted)",marginBottom:2}}>VOLUME</div>
                    <div style={{fontSize:13,fontWeight:600}}>
                      {selectedQuote.volume?(selectedQuote.volume/100000).toFixed(1)+"L":"—"}
                    </div>
                  </div>
                </div>
                <div style={{marginLeft:"auto"}}>
                  <span className={`badge ${selectedQuote.source==="dhan_live"?"badge-green":"badge-yellow"}`}>
                    {selectedQuote.source==="dhan_live"?"● LIVE":"○ SIMULATED"}
                  </span>
                </div>
              </> : <div style={{color:"var(--muted)",fontSize:12}}>Waiting for data...</div>}
            </div>
            {selectedQuote && (
              <div style={{padding:"10px 24px",display:"flex",gap:32,fontSize:11,color:"var(--muted)"}}>
                <span>Range:{" "}
                  <strong style={{color:"var(--red)"}}>₹{Number(selectedQuote.low).toLocaleString()}</strong>
                  {" — "}
                  <strong style={{color:"var(--green)"}}>₹{Number(selectedQuote.high).toLocaleString()}</strong>
                </span>
                <span>Prev Close:{" "}
                  <strong style={{color:"var(--text)"}}>₹{Number(selectedQuote.close).toLocaleString()}</strong>
                </span>
                <span style={{marginLeft:"auto",
                  color:selectedQuote.source==="dhan_live"?"var(--green)":"var(--yellow)"}}>
                  {selectedQuote.source==="dhan_live"
                    ? isLive?"✓ WebSocket live":"✓ REST live"
                    : "⚠ Simulated"}
                </span>
              </div>
            )}
          </div>

          <CandleChartPanel symbol={selected} ltp={selectedQuote?.ltp} />

          <div className="card" style={{marginTop:16}}>
            <div className="card-header">
              <span className="card-title">MARKET OVERVIEW</span>
              <span className="card-badge" style={{color:isLive?"var(--green)":"var(--muted)"}}>
                {isLive?"● LIVE":"○ POLL"}
              </span>
            </div>
            <table className="data-table">
              <thead><tr>
                {["SYMBOL","LTP","CHANGE","CHG %","OPEN","HIGH","LOW","VOLUME","DATA",""].map(h=>(
                  <th key={h}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {watchlist.map(sym => {
                  const q   = quotesMap[sym];
                  const pos = (q?.change_pct ?? 0) >= 0;
                  if (!q) return (
                    <tr key={sym}>
                      <td className="symbol">{sym}</td>
                      <td colSpan={9} style={{color:"var(--muted)",fontSize:11}}>loading...</td>
                    </tr>
                  );
                  return (
                    <tr key={sym} onClick={()=>setSelected(sym)}
                      style={{cursor:"pointer",background:selected===sym?"var(--green-dim)":undefined}}>
                      <td className="symbol" style={{color:selected===sym?"var(--green)":undefined}}>{sym}</td>
                      <td style={{fontWeight:700}}>₹{Number(q.ltp).toLocaleString()}</td>
                      <td style={{color:pos?"var(--green)":"var(--red)"}}>
                        {pos?"+":""}₹{Number(q.change).toFixed(2)}
                      </td>
                      <td style={{color:pos?"var(--green)":"var(--red)",fontWeight:600}}>
                        {pos?"▲":"▼"} {Math.abs(q.change_pct).toFixed(2)}%
                      </td>
                      <td style={{fontSize:11}}>₹{Number(q.open).toLocaleString()}</td>
                      <td style={{fontSize:11,color:"var(--green)"}}>₹{Number(q.high).toLocaleString()}</td>
                      <td style={{fontSize:11,color:"var(--red)"}}>₹{Number(q.low).toLocaleString()}</td>
                      <td style={{fontSize:11,color:"var(--muted)"}}>
                        {q.volume?(q.volume/100000).toFixed(1)+"L":"—"}
                      </td>
                      <td>
                        <span className={`badge ${q.source==="dhan_live"?"badge-green":"badge-yellow"}`}
                          style={{fontSize:9}}>
                          {q.source==="dhan_live"?"LIVE":"SIM"}
                        </span>
                      </td>
                      <td>
                        <button onClick={e=>{e.stopPropagation();removeMutation.mutate(sym);}}
                          style={{background:"transparent",border:"none",color:"var(--muted)",
                            cursor:"pointer",fontSize:11,opacity:0.4}}>✕</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Layout>
  );
}

/* ── Add Symbol Panel ─────────────────────────────────────────────────────── */
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
    onSuccess: (_, inst) => {
      toast.success(`${inst.symbol} added to watchlist`);
      onAdded();
    },
    onError: () => toast.error("Failed to add symbol"),
  });

  useEffect(() => {
    if (query.length < 2) { setResults([]); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api.get(`/market/instruments/search?q=${query}`).then(r=>r.data);
        setResults(data);
      } catch {}
      setLoading(false);
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="card" style={{marginBottom:16}}>
      <div className="card-header"><span className="card-title">ADD SYMBOL TO WATCHLIST</span></div>
      <div style={{padding:"16px 20px 20px"}}>
        <p style={{fontSize:12,color:"var(--muted)",marginBottom:12}}>
          Search across all NSE equity instruments from Dhan's instrument master.
        </p>
        <div style={{position:"relative",maxWidth:500}}>
          <input
            className="field-input"
            value={query}
            onChange={e=>setQuery(e.target.value)}
            placeholder="Search symbol or company name e.g. HDFC, Tata, ZOMATO..."
            style={{paddingRight:40}}
            autoFocus
          />
          {loading && <span style={{position:"absolute",right:12,top:"50%",
            transform:"translateY(-50%)",color:"var(--muted)",fontSize:11}}>...</span>}
        </div>

        {results.length > 0 && (
          <div style={{
            marginTop:8,border:"1px solid var(--border)",
            background:"var(--surface)",maxHeight:300,overflowY:"auto",maxWidth:500,
          }}>
            {results.map(inst => (
              <div key={inst.security_id}
                style={{
                  padding:"10px 14px",display:"flex",
                  justifyContent:"space-between",alignItems:"center",
                  borderBottom:"1px solid var(--border)",cursor:"pointer",
                }}
                onMouseEnter={e=>(e.currentTarget.style.background="var(--green-dim)")}
                onMouseLeave={e=>(e.currentTarget.style.background="")}>
                <div>
                  <span style={{fontWeight:700,color:"var(--green)",fontSize:13}}>{inst.symbol}</span>
                  <span style={{fontSize:11,color:"var(--muted)",marginLeft:10}}>{inst.name}</span>
                </div>
                <div style={{display:"flex",gap:8,alignItems:"center"}}>
                  <span style={{fontSize:10,color:"var(--muted)"}}>{inst.exchange} · {inst.series}</span>
                  <button
                    className="connect-btn"
                    style={{padding:"3px 10px",fontSize:10}}
                    onClick={()=>addMutation.mutate(inst)}
                    disabled={addMutation.isPending}
                  >+ ADD</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {query.length >= 2 && !loading && results.length === 0 && (
          <div style={{fontSize:12,color:"var(--muted)",marginTop:8}}>
            No instruments found for "{query}"
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Candle Chart ─────────────────────────────────────────────────────────── */
function CandleChartPanel({ symbol, ltp }: { symbol: string; ltp?: number }) {
  const chartRef  = useRef<HTMLDivElement>(null);
  const chartObj  = useRef<any>(null);
  const seriesRef = useRef<any>({});
  const prevLtp   = useRef<number>(0);

  const { data } = useQuery({
    queryKey: ["candles", symbol, "5"],
    queryFn:  () => api.get(`/market/candles?symbol=${symbol}&timeframe=5&bars=200`).then(r=>r.data),
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = createChart(chartRef.current, {
      layout:{background:{type:ColorType.Solid,color:"#0d1117"},textColor:"#4a5568"},
      grid:{vertLines:{color:"rgba(255,255,255,0.03)"},horzLines:{color:"rgba(255,255,255,0.03)"}},
      rightPriceScale:{borderColor:"#30363d"},
      timeScale:{borderColor:"#30363d",timeVisible:true},
      width:chartRef.current.clientWidth, height:280,
    });
    chartObj.current = chart;
    seriesRef.current.candles = chart.addCandlestickSeries({
      upColor:"#00ff88",downColor:"#ff4466",
      borderUpColor:"#00ff88",borderDownColor:"#ff4466",
      wickUpColor:"#00ff88",wickDownColor:"#ff4466",
    });
    seriesRef.current.volume = chart.addHistogramSeries({
      color:"rgba(0,255,136,0.3)",priceFormat:{type:"volume"},priceScaleId:"vol",
    });
    chart.priceScale("vol").applyOptions({scaleMargins:{top:0.85,bottom:0}});
    const ro = new ResizeObserver(()=>{
      if(chartRef.current) chart.applyOptions({width:chartRef.current.clientWidth});
    });
    ro.observe(chartRef.current);
    return ()=>{ ro.disconnect(); chart.remove(); };
  }, []);

  useEffect(()=>{
    if(!data?.candles||!chartObj.current) return;
    seriesRef.current.candles?.setData(data.candles.map((c:any)=>({
      time:c.time,open:c.open,high:c.high,low:c.low,close:c.close,
    })));
    seriesRef.current.volume?.setData(data.candles.map((c:any)=>({
      time:c.time,value:c.volume,
      color:c.close>=c.open?"rgba(0,255,136,0.3)":"rgba(255,68,102,0.3)",
    })));
    chartObj.current.timeScale().fitContent();
  }, [data]);

  useEffect(()=>{
    if(!ltp||!data?.candles?.length||!seriesRef.current.candles) return;
    if(ltp===prevLtp.current) return;
    prevLtp.current = ltp;
    const last = data.candles[data.candles.length-1];
    seriesRef.current.candles.update({
      time:last.time, open:last.open,
      high:Math.max(last.high,ltp), low:Math.min(last.low,ltp), close:ltp,
    });
  }, [ltp, data]);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{symbol} · 5m CHART</span>
        {ltp && <span style={{fontSize:12,color:"var(--green)",fontWeight:700}}>
          ₹{Number(ltp).toLocaleString()}
        </span>}
      </div>
      <div ref={chartRef} style={{width:"100%"}} />
    </div>
  );
}
