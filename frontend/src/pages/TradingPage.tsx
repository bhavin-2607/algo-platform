import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api, brokerApi } from "@/utils/api";
import toast from "react-hot-toast";

// Only Dhan shown in UI — Shoonya is legacy/hidden
const BROKER_OPTIONS = [
  { value: "dhan", label: "Dhan / DhanHQ",
    desc: "Free Trading API · Data API available · Recommended" },
];

export default function TradingPage() {
  const qc   = useQueryClient();
  const [tab, setTab] = useState<"orders"|"brokers">("brokers");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    broker: "dhan", client_id: "", paper_trading: true,
  });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  const connectMutation = useMutation({
    mutationFn: () => api.post("/brokers", {
      broker:        form.broker,
      client_id:     form.client_id || "DHAN_PAPER",
      paper_trading: form.paper_trading,
    }),
    onSuccess: () => {
      toast.success("Broker account added");
      qc.invalidateQueries({ queryKey: ["brokers"] });
      setShowForm(false);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed"),
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => brokerApi.activate(id),
    onSuccess: () => { toast.success("Broker activated"); qc.invalidateQueries({queryKey:["brokers"]}); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Activation failed"),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => brokerApi.disconnect(id),
    onSuccess: () => { toast.success("Removed"); qc.invalidateQueries({queryKey:["brokers"]}); },
  });

  // Filter out legacy Shoonya accounts from display
  const visibleBrokers = (brokers ?? []).filter((b: any) => b.broker !== "shoonya");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">TRADING</h1>
          <p className="page-sub">Order management & broker connections</p>
        </div>
        <div style={{display:"flex",gap:8}}>
          <div className="tab-switcher">
            <button className={`tab-btn${tab==="orders"  ?" active":""}`} onClick={()=>setTab("orders")}>ORDER BOOK</button>
            <button className={`tab-btn${tab==="brokers" ?" active":""}`} onClick={()=>setTab("brokers")}>BROKERS</button>
          </div>
        </div>
      </div>

      {tab === "brokers" && (
        <div>
          <div className="card">
            <div className="card-header">
              <span className="card-title">CONNECTED BROKERS</span>
              <button className="connect-btn" onClick={() => setShowForm(v=>!v)}>
                {showForm ? "✕ CANCEL" : "+ ADD BROKER"}
              </button>
            </div>

            {showForm && (
              <div style={{padding:"20px 20px 0"}}>
                <div style={{display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12, marginBottom:16}}>
                  <div className="field">
                    <label className="field-label">BROKER</label>
                    <select className="field-input" value={form.broker}
                      onChange={e => setForm(f=>({...f, broker:e.target.value}))}
                      style={{background:"rgba(0,255,136,0.04)", color:"var(--text)", fontFamily:"var(--font)"}}>
                      {BROKER_OPTIONS.map(b => (
                        <option key={b.value} value={b.value}>{b.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label className="field-label">CLIENT ID</label>
                    <input className="field-input" value={form.client_id}
                      onChange={e => setForm(f=>({...f, client_id:e.target.value}))}
                      placeholder="Your Dhan client ID" />
                  </div>
                  <div className="field">
                    <label className="field-label">MODE</label>
                    <div style={{display:"flex"}}>
                      {["Paper","Live"].map((m,i) => (
                        <button key={m} type="button"
                          onClick={() => setForm(f=>({...f, paper_trading: m==="Paper"}))}
                          style={{
                            flex:1, padding:11, fontFamily:"var(--font)", fontSize:11,
                            cursor:"pointer", borderRight:i===0?"none":undefined,
                            border:"1px solid",
                            background: (form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                              ? m==="Paper"?"rgba(255,208,96,0.15)":"rgba(255,68,102,0.1)"
                              : "transparent",
                            borderColor: (form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                              ? m==="Paper"?"rgba(255,208,96,0.4)":"rgba(255,68,102,0.4)"
                              : "var(--border)",
                            color: (form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                              ? m==="Paper"?"var(--yellow)":"var(--red)"
                              : "var(--muted)",
                          }}>{m.toUpperCase()}</button>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="info-box" style={{marginBottom:16}}>
                  <div className="info-icon">ℹ</div>
                  <div>
                    <div className="info-title">DHAN CREDENTIALS</div>
                    <div className="info-body">
                      Add <code>DHAN_CLIENT_ID</code> and <code>DHAN_ACCESS_TOKEN</code> to your{" "}
                      <code>.env</code> file. Generate token at{" "}
                      <strong>web.dhan.co → My Profile → Access DhanHQ APIs</strong>.
                    </div>
                  </div>
                </div>
                <button className={`auth-btn${connectMutation.isPending?" loading":""}`}
                  onClick={() => connectMutation.mutate()}
                  disabled={connectMutation.isPending}
                  style={{maxWidth:220, marginBottom:20}}>
                  {connectMutation.isPending ? "ADDING..." : "ADD BROKER →"}
                </button>
              </div>
            )}

            {visibleBrokers.length === 0 && !showForm && (
              <div className="empty-state">No broker connected. Add Dhan to start trading.</div>
            )}

            {visibleBrokers.map((b: any) => (
              <div key={b.id} style={{
                padding:"16px 20px", borderTop:"1px solid var(--border)",
                display:"flex", alignItems:"center", justifyContent:"space-between",
              }}>
                <div style={{display:"flex", alignItems:"center", gap:14}}>
                  <div style={{
                    width:36, height:36, borderRadius:4,
                    background:"rgba(0,255,136,0.1)",
                    border:"1px solid rgba(0,255,136,0.3)",
                    display:"flex", alignItems:"center", justifyContent:"center",
                    fontSize:13, fontWeight:700, color:"var(--green)",
                  }}>{b.broker[0].toUpperCase()}</div>
                  <div>
                    <div style={{fontWeight:700, fontSize:13}}>
                      {b.broker.toUpperCase()}
                    </div>
                    <div style={{fontSize:11, color:"var(--muted)"}}>
                      Client ID: {b.client_id}
                    </div>
                  </div>
                </div>
                <div style={{display:"flex", alignItems:"center", gap:10}}>
                  <span className={`badge ${b.paper_trading ? "badge-yellow" : "badge-green"}`}>
                    {b.paper_trading ? "PAPER" : "LIVE"}
                  </span>
                  <span className={`badge ${b.is_active ? "badge-green" : "badge-gray"}`}>
                    {b.is_active ? "● ACTIVE" : "○ INACTIVE"}
                  </span>
                  {!b.is_active && (
                    <button className="connect-btn" style={{padding:"5px 12px", fontSize:10}}
                      onClick={() => activateMutation.mutate(b.id)}
                      disabled={activateMutation.isPending}>
                      {activateMutation.isPending ? "..." : "⚡ ACTIVATE"}
                    </button>
                  )}
                  <button className="exit-btn"
                    onClick={() => removeMutation.mutate(b.id)}>REMOVE</button>
                </div>
              </div>
            ))}
          </div>

          <div className="info-box" style={{marginTop:16}}>
            <div className="info-icon">ℹ</div>
            <div>
              <div className="info-title">ABOUT PAPER TRADING</div>
              <div className="info-body">
                Paper mode simulates all orders without touching real capital.
                Use it to validate strategies before going live.
                Switch to Live mode only after thorough paper testing.
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "orders" && (
        <div className="card">
          <div className="card-header"><span className="card-title">ORDER BOOK</span></div>
          <div className="empty-state">No orders today.</div>
        </div>
      )}
    </Layout>
  );
}
