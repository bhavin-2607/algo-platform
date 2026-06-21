import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

const UNDERLYINGS = ["NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"];

export default function OptionsPage() {
  const qc = useQueryClient();
  const [underlying, setUnderlying] = useState("NIFTY50");
  const [expiry,     setExpiry]     = useState("");
  const [expiryType, setExpiryType] = useState<"all"|"weekly"|"monthly">("all");
  const [orderPanel, setOrderPanel] = useState<any>(null);
  const [strikeFilter, setStrikeFilter] = useState<"all"|"itm"|"atm"|"otm">("all");

  // Fetch expiry list
  const { data: expiryData } = useQuery({
    queryKey: ["options-expiry", underlying],
    queryFn: () => api.get(`/options/expiry?underlying=${underlying}`).then(r => r.data),
    enabled: !!underlying,
  });

  // Auto-select first expiry
  useEffect(() => {
    if (expiryData?.expiries?.length && !expiry) {
      setExpiry(expiryData.expiries[0].date);
    }
  }, [expiryData]);

  useEffect(() => { setExpiry(""); }, [underlying]);

  // Fetch option chain
  const { data: chainData, isLoading: chainLoading, refetch: refetchChain } = useQuery({
    queryKey: ["options-chain", underlying, expiry],
    queryFn: () => api.get(`/options/chain?underlying=${underlying}&expiry=${expiry}`).then(r => r.data),
    enabled: !!underlying && !!expiry,
    refetchInterval: 5000,
  });

  // Options watchlist
  const { data: optWatchlist } = useQuery({
    queryKey: ["options-watchlist"],
    queryFn: () => api.get("/options/watchlist").then(r => r.data),
    refetchInterval: 5000,
  });

  const { data: optLive } = useQuery({
    queryKey: ["options-live"],
    queryFn: () => api.get("/options/watchlist/live").then(r => r.data),
    refetchInterval: 4000,
    enabled: (optWatchlist ?? []).length > 0,
  });

  const addMutation = useMutation({
    mutationFn: (item: any) => api.post("/options/watchlist", item),
    onSuccess: () => { toast.success("Added to watchlist"); qc.invalidateQueries({queryKey:["options-watchlist"]}); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed"),
  });
  const removeMutation = useMutation({
    mutationFn: (sid: string) => api.delete(`/options/watchlist/${sid}`),
    onSuccess: () => { toast.success("Removed"); qc.invalidateQueries({queryKey:["options-watchlist"]}); },
  });

  const atm = chainData?.atm_strike ?? 0;
  const ltp = chainData?.underlying_ltp ?? 0;
  const lotSize = chainData?.lot_size ?? expiryData?.lot_size ?? 75;

  const filteredStrikes = (chainData?.strikes ?? []).filter((s: any) => {
    if (strikeFilter === "all") return true;
    if (strikeFilter === "atm") return Math.abs(s.strike - atm) <= (underlying === "BANKNIFTY" ? 200 : 100);
    if (strikeFilter === "itm") return s.strike < atm;
    if (strikeFilter === "otm") return s.strike > atm;
    return true;
  });

  const addedSids = new Set((optWatchlist ?? []).map((w: any) => w.security_id));

  const filteredExpiries = (expiryData?.expiries ?? []).filter((e: any) =>
    expiryType === "all" || e.type === expiryType
  );

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">OPTIONS</h1>
          <p className="page-sub">Option chain with Greeks — NIFTY50 & BANKNIFTY</p>
        </div>
        <div style={{display:"flex", gap:8, alignItems:"center"}}>
          {/* Underlying selector */}
          {UNDERLYINGS.map(u => (
            <button key={u}
              onClick={() => setUnderlying(u)}
              style={{
                padding:"6px 14px", fontSize:10, fontFamily:"var(--font)",
                letterSpacing:1.5, cursor:"pointer", fontWeight:700,
                background: underlying===u ? "rgba(0,255,136,0.15)" : "transparent",
                border: `1px solid ${underlying===u ? "rgba(0,255,136,0.5)" : "var(--border)"}`,
                color: underlying===u ? "var(--green)" : "var(--muted)",
              }}>{u}
            </button>
          ))}
        </div>
      </div>

      <div style={{display:"flex", gap:16, flexDirection:"column"}}>

        {/* ── Controls row ─────────────────────────────────────── */}
        <div style={{display:"flex", gap:12, alignItems:"center", flexWrap:"wrap"}}>
          {/* Expiry type filter */}
          <div style={{display:"flex", border:"1px solid var(--border)"}}>
            {(["all","weekly","monthly"] as const).map((t,i) => (
              <button key={t} onClick={() => setExpiryType(t)} style={{
                padding:"6px 12px", fontSize:10, fontFamily:"var(--font)",
                cursor:"pointer", letterSpacing:1,
                borderRight: i < 2 ? "1px solid var(--border)" : undefined,
                background: expiryType===t ? "rgba(0,255,136,0.1)" : "transparent",
                color: expiryType===t ? "var(--green)" : "var(--muted)",
                border: "none",
              }}>{t.toUpperCase()}</button>
            ))}
          </div>

          {/* Expiry dropdown */}
          <select value={expiry} onChange={e => setExpiry(e.target.value)}
            style={{
              background:"var(--surface)", color:"var(--text)",
              border:"1px solid var(--border)", padding:"6px 12px",
              fontFamily:"var(--font)", fontSize:11, minWidth:160, cursor:"pointer",
            }}>
            <option value="">Select Expiry</option>
            {filteredExpiries.map((e: any) => (
              <option key={e.date} value={e.date}>
                {e.display} ({e.days_to_expiry}D) — {e.type}
              </option>
            ))}
          </select>

          {/* Strike filter */}
          <div style={{display:"flex", border:"1px solid var(--border)"}}>
            {(["all","itm","atm","otm"] as const).map((f,i) => (
              <button key={f} onClick={() => setStrikeFilter(f)} style={{
                padding:"6px 10px", fontSize:10, fontFamily:"var(--font)",
                cursor:"pointer", letterSpacing:1,
                borderRight: i < 3 ? "1px solid var(--border)" : undefined,
                background: strikeFilter===f ? "rgba(0,255,136,0.1)" : "transparent",
                color: strikeFilter===f ? "var(--green)" : "var(--muted)",
                border: "none",
              }}>{f.toUpperCase()}</button>
            ))}
          </div>

          {/* Underlying LTP */}
          {ltp > 0 && (
            <div style={{marginLeft:"auto", fontSize:12, color:"var(--muted)"}}>
              {underlying} <span style={{color:"var(--green)", fontWeight:700, fontSize:14}}>
                ₹{ltp.toLocaleString()}
              </span>
              <span style={{marginLeft:8, fontSize:10}}>ATM: {atm}</span>
            </div>
          )}
        </div>

        {/* ── Option Chain Table ───────────────────────────────── */}
        <div className="card" style={{overflowX:"auto"}}>
          <div className="card-header">
            <span className="card-title">OPTION CHAIN — {underlying} {expiry}</span>
            <span style={{fontSize:10, color:"var(--muted)"}}>Lot Size: {lotSize} · Rate limit: 3s</span>
          </div>

          {chainLoading && (
            <div style={{padding:"30px", textAlign:"center", color:"var(--muted)", fontSize:12}}>
              Loading option chain...
            </div>
          )}

          {!chainLoading && chainData && (
            <table style={{width:"100%", borderCollapse:"collapse", fontSize:11, fontFamily:"var(--font)"}}>
              <thead>
                <tr style={{background:"rgba(0,0,0,0.3)"}}>
                  {/* CE side */}
                  <th style={thStyle("ce")}>OI (CE)</th>
                  <th style={thStyle("ce")}>IV</th>
                  <th style={thStyle("ce")}>Delta</th>
                  <th style={thStyle("ce")}>Theta</th>
                  <th style={thStyle("ce")}>Volume</th>
                  <th style={thStyle("ce")}>BID</th>
                  <th style={thStyle("ce")}>LTP (CE)</th>
                  <th style={thStyle("ce")}>ADD</th>
                  {/* Strike */}
                  <th style={{...thStyle("strike"), minWidth:90}}>STRIKE</th>
                  {/* PE side */}
                  <th style={thStyle("pe")}>ADD</th>
                  <th style={thStyle("pe")}>LTP (PE)</th>
                  <th style={thStyle("pe")}>BID</th>
                  <th style={thStyle("pe")}>Volume</th>
                  <th style={thStyle("pe")}>Theta</th>
                  <th style={thStyle("pe")}>Delta</th>
                  <th style={thStyle("pe")}>IV</th>
                  <th style={thStyle("pe")}>OI (PE)</th>
                </tr>
              </thead>
              <tbody>
                {filteredStrikes.map((s: any) => {
                  const isATM = s.strike === atm;
                  const ceAdded = addedSids.has(s.ce?.security_id);
                  const peAdded = addedSids.has(s.pe?.security_id);
                  return (
                    <tr key={s.strike} style={{
                      borderBottom:"1px solid var(--border)",
                      background: isATM ? "rgba(0,255,136,0.05)" : "transparent",
                    }}
                      onMouseEnter={e=>(e.currentTarget.style.background=isATM?"rgba(0,255,136,0.08)":"rgba(255,255,255,0.02)")}
                      onMouseLeave={e=>(e.currentTarget.style.background=isATM?"rgba(0,255,136,0.05)":"transparent")}
                    >
                      {/* CE */}
                      <td style={tdStyle("ce")}>{fmtOI(s.ce?.oi)}</td>
                      <td style={tdStyle("ce")}>{s.ce?.iv?.toFixed(1)}%</td>
                      <td style={tdStyle("ce")}>{s.ce?.delta?.toFixed(3)}</td>
                      <td style={tdStyle("ce")}>{s.ce?.theta?.toFixed(2)}</td>
                      <td style={tdStyle("ce")}>{fmtOI(s.ce?.volume)}</td>
                      <td style={tdStyle("ce")}>{s.ce?.bid}</td>
                      <td style={{...tdStyle("ce"), fontWeight:700, color:"var(--green)"}}>
                        {s.ce?.ltp}
                      </td>
                      <td style={tdStyle("ce")}>
                        {s.ce?.security_id && (
                          <button onClick={() => {
                            if (ceAdded) return;
                            addMutation.mutate({
                              underlying, strike: s.strike, option_type: "CE",
                              security_id: s.ce.security_id, expiry,
                              symbol: `${underlying} ${s.strike} CE`,
                              exchange_segment: "NSE_FNO", lot_size: lotSize,
                            });
                          }} style={addBtnStyle(ceAdded)}>
                            {ceAdded ? "✓" : "+"}
                          </button>
                        )}
                      </td>
                      {/* Strike */}
                      <td style={{
                        textAlign:"center", fontWeight:700,
                        fontSize: isATM ? 13 : 11,
                        color: isATM ? "var(--green)" : "var(--text)",
                        padding:"8px 6px",
                        background: isATM ? "rgba(0,255,136,0.1)" : "transparent",
                        borderLeft:"1px solid var(--border)",
                        borderRight:"1px solid var(--border)",
                      }}>
                        {s.strike}
                        {isATM && <div style={{fontSize:8,color:"var(--green)",letterSpacing:1}}>ATM</div>}
                      </td>
                      {/* PE */}
                      <td style={tdStyle("pe")}>
                        {s.pe?.security_id && (
                          <button onClick={() => {
                            if (peAdded) return;
                            addMutation.mutate({
                              underlying, strike: s.strike, option_type: "PE",
                              security_id: s.pe.security_id, expiry,
                              symbol: `${underlying} ${s.strike} PE`,
                              exchange_segment: "NSE_FNO", lot_size: lotSize,
                            });
                          }} style={addBtnStyle(peAdded)}>
                            {peAdded ? "✓" : "+"}
                          </button>
                        )}
                      </td>
                      <td style={{...tdStyle("pe"), fontWeight:700, color:"var(--red)"}}>
                        {s.pe?.ltp}
                      </td>
                      <td style={tdStyle("pe")}>{s.pe?.bid}</td>
                      <td style={tdStyle("pe")}>{fmtOI(s.pe?.volume)}</td>
                      <td style={tdStyle("pe")}>{s.pe?.theta?.toFixed(2)}</td>
                      <td style={tdStyle("pe")}>{s.pe?.delta?.toFixed(3)}</td>
                      <td style={tdStyle("pe")}>{s.pe?.iv?.toFixed(1)}%</td>
                      <td style={tdStyle("pe")}>{fmtOI(s.pe?.oi)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {!chainLoading && !chainData && expiry && (
            <div style={{padding:"30px", textAlign:"center", color:"var(--muted)", fontSize:12}}>
              Select an expiry to load option chain
            </div>
          )}
        </div>

        {/* ── Options Watchlist ──────────────────────────────────── */}
        {optWatchlist && optWatchlist.length > 0 && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">MY OPTIONS ({optWatchlist.length})</span>
              <span style={{fontSize:10, color:"var(--muted)"}}>Live data via NFO_FNO segment</span>
            </div>
            <table style={{width:"100%", borderCollapse:"collapse", fontSize:11, fontFamily:"var(--font)"}}>
              <thead>
                <tr style={{background:"rgba(0,0,0,0.3)"}}>
                  {["SYMBOL","TYPE","STRIKE","EXPIRY","LTP","CHG%","OI","LOT SIZE","ACTIONS"].map(h => (
                    <th key={h} style={{padding:"8px 12px",fontSize:9,letterSpacing:1.5,
                      color:"var(--muted)",textAlign:"left",borderBottom:"1px solid var(--border)"}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {optWatchlist.map((w: any) => (
                  <tr key={w.security_id} style={{borderBottom:"1px solid var(--border)"}}
                    onMouseEnter={e=>(e.currentTarget.style.background="rgba(255,255,255,0.02)")}
                    onMouseLeave={e=>(e.currentTarget.style.background="transparent")}
                  >
                    <td style={{padding:"10px 12px", fontWeight:700}}>
                      <div>{w.symbol}</div>
                      <div style={{fontSize:9, color:"var(--muted)", marginTop:2}}>{w.exchange_segment} · ID: {w.security_id}</div>
                    </td>
                    <td style={{padding:"10px 12px"}}>
                      <span className={`badge ${w.option_type==="CE"?"badge-green":"badge-red"}`}>
                        {w.option_type}
                      </span>
                    </td>
                    <td style={{padding:"10px 12px", fontWeight:700}}>₹{w.strike}</td>
                    <td style={{padding:"10px 12px", color:"var(--muted)", fontSize:11}}>
                      {new Date(w.expiry).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"})}
                    </td>
                    <td style={{padding:"10px 12px", fontWeight:700,
                      color: (optLive?.[w.security_id]?.ltp ?? 0) > 0 ? "var(--green)" : "var(--muted)"}}>
                      {optLive?.[w.security_id]?.ltp ? `₹${optLive[w.security_id].ltp}` : "—"}
                    </td>
                    <td style={{padding:"10px 12px",
                      color: (optLive?.[w.security_id]?.change_pct ?? 0) >= 0 ? "var(--green)" : "var(--red)"}}>
                      {optLive?.[w.security_id]?.change_pct != null
                        ? `${optLive[w.security_id].change_pct >= 0 ? "+" : ""}${optLive[w.security_id].change_pct}%`
                        : "—"}
                    </td>
                    <td style={{padding:"10px 12px", color:"var(--muted)", fontSize:11}}>
                      {optLive?.[w.security_id]?.oi
                        ? (optLive[w.security_id].oi >= 1e6
                          ? `${(optLive[w.security_id].oi/1e6).toFixed(1)}M`
                          : `${(optLive[w.security_id].oi/1e3).toFixed(0)}K`)
                        : "—"}
                    </td>
                    <td style={{padding:"10px 12px"}}>{w.lot_size}</td>
                    <td style={{padding:"10px 12px"}}>
                      <div style={{display:"flex", gap:6}}>
                        <button onClick={() => setOrderPanel({...w, side:"BUY"})}
                          style={orderBtnStyle("BUY")}>BUY</button>
                        <button onClick={() => setOrderPanel({...w, side:"SELL"})}
                          style={orderBtnStyle("SELL")}>SELL</button>
                        <button onClick={() => removeMutation.mutate(w.security_id)}
                          style={{...orderBtnStyle("SELL"), color:"var(--muted)", borderColor:"var(--border)"}}>✕</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Order Panel ────────────────────────────────────────── */}
        {orderPanel && (
          <OptionsOrderPanel
            item={orderPanel}
            onClose={() => setOrderPanel(null)}
          />
        )}
      </div>
    </Layout>
  );
}

/* ── Options Order Panel ─────────────────────────────────────────────────── */
function OptionsOrderPanel({ item, onClose }: { item: any; onClose: () => void }) {
  const [side,      setSide]      = useState<"BUY"|"SELL">(item.side || "BUY");
  const [lots,      setLots]      = useState(1);
  const [orderType, setOrderType] = useState("MARKET");
  const [product,   setProduct]   = useState("INTRADAY");
  const [price,     setPrice]     = useState("");
  const [confirm,   setConfirm]   = useState(false);

  const qty = lots * (item.lot_size || 75);

  const orderMutation = useMutation({
    mutationFn: () => api.post("/terminal/order", {
      symbol:           item.symbol,
      security_id:      item.security_id,
      exchange_segment: item.exchange_segment || "NSE_FNO",
      transaction_type: side,
      quantity:         qty,
      order_type:       orderType,
      product_type:     product,
      price:            orderType === "LIMIT" ? parseFloat(price) : 0,
      trigger_price:    0,
    }),
    onSuccess: (res: any) => {
      toast.success(`✅ ${side} order placed — ${res.data?.order_id ?? ""}`);
      onClose();
    },
    onError: (e: any) => {
      const d = e.response?.data?.detail;
      const msg = Array.isArray(d) ? d.map((x:any)=>x.msg).join(", ")
        : typeof d === "string" ? d : d?.error_message || "Order failed";
      toast.error(msg);
      setConfirm(false);
    },
  });

  return (
    <div style={{
      position:"fixed", top:0, left:0, right:0, bottom:0,
      background:"rgba(0,0,0,0.7)", display:"flex",
      alignItems:"center", justifyContent:"center", zIndex:1000,
    }} onClick={e=>{if(e.target===e.currentTarget)onClose();}}>
      <div style={{
        background:"var(--surface)", border:"1px solid var(--border)",
        width:420, padding:24,
      }}>
        <div style={{display:"flex", justifyContent:"space-between", marginBottom:16}}>
          <div>
            <div style={{fontWeight:700, fontSize:13}}>{item.symbol}</div>
            <div style={{fontSize:10, color:"var(--muted)", marginTop:2}}>
              {item.exchange_segment} · Lot: {item.lot_size}
            </div>
          </div>
          <button onClick={onClose} style={{background:"transparent",border:"none",
            color:"var(--muted)",cursor:"pointer",fontSize:16}}>✕</button>
        </div>

        {/* BUY / SELL toggle */}
        <div style={{display:"flex", marginBottom:16}}>
          {(["BUY","SELL"] as const).map((s,i) => (
            <button key={s} onClick={() => setSide(s)} style={{
              flex:1, padding:10, fontFamily:"var(--font)", fontSize:11,
              fontWeight:700, cursor:"pointer",
              borderRight: i===0?"none":undefined,
              border:"1px solid",
              background: side===s
                ? s==="BUY"?"rgba(0,255,136,0.15)":"rgba(255,68,102,0.15)"
                : "transparent",
              borderColor: side===s
                ? s==="BUY"?"rgba(0,255,136,0.5)":"rgba(255,68,102,0.5)"
                : "var(--border)",
              color: side===s
                ? s==="BUY"?"var(--green)":"var(--red)"
                : "var(--muted)",
            }}>{s}</button>
          ))}
        </div>

        {/* Order type + product */}
        <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12}}>
          <div className="field">
            <label className="field-label">ORDER TYPE</label>
            <select className="field-input" value={orderType} onChange={e=>setOrderType(e.target.value)}
              style={{background:"var(--surface)",color:"var(--text)",fontFamily:"var(--font)"}}>
              <option>MARKET</option>
              <option>LIMIT</option>
            </select>
          </div>
          <div className="field">
            <label className="field-label">PRODUCT</label>
            <select className="field-input" value={product} onChange={e=>setProduct(e.target.value)}
              style={{background:"var(--surface)",color:"var(--text)",fontFamily:"var(--font)"}}>
              <option value="INTRADAY">INTRADAY (MIS)</option>
              <option value="CNC">DELIVERY (NRML)</option>
            </select>
          </div>
        </div>

        {/* Lots + Price */}
        <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:16}}>
          <div className="field">
            <label className="field-label">LOTS (1 lot = {item.lot_size} qty)</label>
            <input className="field-input" type="number" min={1} value={lots}
              onChange={e=>setLots(parseInt(e.target.value)||1)} />
          </div>
          {orderType === "LIMIT" && (
            <div className="field">
              <label className="field-label">PRICE (₹)</label>
              <input className="field-input" type="number" value={price}
                onChange={e=>setPrice(e.target.value)} placeholder="0.00" />
            </div>
          )}
        </div>

        {/* Summary */}
        <div style={{padding:"10px 12px", background:"rgba(0,0,0,0.2)",
          border:"1px solid var(--border)", marginBottom:16, fontSize:11}}>
          <div style={{display:"flex", justifyContent:"space-between"}}>
            <span style={{color:"var(--muted)"}}>Total Quantity</span>
            <span style={{fontWeight:700}}>{qty} shares</span>
          </div>
          <div style={{display:"flex", justifyContent:"space-between", marginTop:4}}>
            <span style={{color:"var(--muted)"}}>Segment</span>
            <span>{item.exchange_segment}</span>
          </div>
          <div style={{display:"flex", justifyContent:"space-between", marginTop:4}}>
            <span style={{color:"var(--muted)"}}>Strike / Type</span>
            <span>₹{item.strike} {item.option_type}</span>
          </div>
        </div>

        {!confirm ? (
          <button onClick={() => setConfirm(true)} style={{
            width:"100%", padding:12, fontFamily:"var(--font)",
            fontSize:12, fontWeight:700, cursor:"pointer",
            background: side==="BUY" ? "rgba(0,255,136,0.2)" : "rgba(255,68,102,0.2)",
            border: `1px solid ${side==="BUY"?"rgba(0,255,136,0.5)":"rgba(255,68,102,0.5)"}`,
            color: side==="BUY" ? "var(--green)" : "var(--red)",
          }}>
            {side} {lots} LOT{lots>1?"S":""} × {item.symbol}
          </button>
        ) : (
          <div style={{display:"flex", gap:8}}>
            <button onClick={() => orderMutation.mutate()}
              disabled={orderMutation.isPending}
              style={{
                flex:1, padding:12, fontFamily:"var(--font)", fontSize:12,
                fontWeight:700, cursor:"pointer",
                background: side==="BUY" ? "rgba(0,255,136,0.3)" : "rgba(255,68,102,0.3)",
                border: `2px solid ${side==="BUY"?"var(--green)":"var(--red)"}`,
                color: side==="BUY" ? "var(--green)" : "var(--red)",
              }}>
              {orderMutation.isPending ? "PLACING..." : `CONFIRM ${side}`}
            </button>
            <button onClick={() => setConfirm(false)} style={{
              padding:"12px 20px", fontFamily:"var(--font)", fontSize:11,
              cursor:"pointer", background:"transparent",
              border:"1px solid var(--border)", color:"var(--muted)",
            }}>CANCEL</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function fmtOI(v?: number) {
  if (!v) return "—";
  if (v >= 1_000_000) return `${(v/1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `${(v/1_000).toFixed(0)}K`;
  return String(v);
}

function thStyle(side: "ce"|"pe"|"strike"): React.CSSProperties {
  return {
    padding:"8px 8px", fontSize:9, letterSpacing:1.2,
    color: side==="ce" ? "rgba(0,255,136,0.7)" : side==="pe" ? "rgba(255,68,102,0.7)" : "var(--text)",
    textAlign: side==="pe" ? "right" : "left",
    borderBottom:"1px solid var(--border)",
    borderRight:"1px solid rgba(255,255,255,0.05)",
    whiteSpace:"nowrap",
  };
}

function tdStyle(side: "ce"|"pe"): React.CSSProperties {
  return {
    padding:"7px 8px", textAlign: side==="pe" ? "right" : "left",
    color:"var(--muted)", borderRight:"1px solid rgba(255,255,255,0.03)",
    fontSize:11,
  };
}

function addBtnStyle(added: boolean): React.CSSProperties {
  return {
    width:24, height:24, fontSize:13, cursor: added ? "default" : "pointer",
    fontFamily:"var(--font)", fontWeight:700,
    background: added ? "rgba(0,255,136,0.15)" : "rgba(0,255,136,0.08)",
    border: `1px solid ${added ? "rgba(0,255,136,0.5)" : "var(--border)"}`,
    color: added ? "var(--green)" : "var(--muted)",
    display:"flex", alignItems:"center", justifyContent:"center",
  };
}

function orderBtnStyle(side: "BUY"|"SELL"): React.CSSProperties {
  return {
    padding:"4px 12px", fontSize:10, cursor:"pointer",
    fontFamily:"var(--font)", fontWeight:700,
    background: side==="BUY" ? "rgba(0,255,136,0.15)" : "rgba(255,68,102,0.15)",
    border: `1px solid ${side==="BUY" ? "rgba(0,255,136,0.4)" : "rgba(255,68,102,0.4)"}`,
    color: side==="BUY" ? "var(--green)" : "var(--red)",
  };
}
