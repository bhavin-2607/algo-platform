import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api, brokerApi } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

const BROKER_OPTIONS = [
  { value: "dhan", label: "Dhan / DhanHQ",
    desc: "Free Trading API · Data API available · Recommended" },
];

export default function TradingPage() {
  const { data: orderbook, isLoading: obLoading } = useQuery({
    queryKey: ["orderbook"],
    queryFn: () => api.get("/terminal/orderbook").then(r => r.data),
    refetchInterval: 10000,
  });
  const qc = useQueryClient();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<"orders">("orders");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ broker:"dhan", client_id:"", access_token:"", paper_trading:true });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  const connectMutation = useMutation({
    mutationFn: () => api.post("/brokers", {
      broker: form.broker, client_id: form.client_id || "DHAN_PAPER",
      paper_trading: form.paper_trading,
    }).then(async (res) => {
      // If live broker with token provided, save credentials too
      if (!form.paper_trading && form.access_token && form.client_id) {
        await api.post("/settings/dhan-credentials", {
          client_id: form.client_id,
          access_token: form.access_token,
        });
      }
      return res;
    }),
    onSuccess: () => { toast.success("Broker account added"); qc.invalidateQueries({queryKey:["brokers"]}); setShowForm(false); },
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

  const visibleBrokers = (brokers ?? []).filter((b: any) => b.broker !== "shoonya");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">TRADING</h1>
          <p className="page-sub">Order management & broker connections</p>
        </div>
        <div style={{display:"flex", gap:8}}>
          <div className="tab-switcher">
            <button className={`tab-btn${tab==="orders"?"  active":""}`} onClick={()=>setTab("orders")}>ORDER BOOK</button>

          </div>
        </div>
      </div>


      {/* ── ORDER BOOK TAB ───────────────────────────────────────────────────── */}
      {tab === "orders" && (
        <div className="card">
          <div className="card-header"><span className="card-title">ORDER BOOK</span></div>
          <div className="empty-state">No orders today.</div>
        </div>
      )}
    </Layout>
  );
}

// ── Broker Row with inline Edit + Deactivate ──────────────────────────────────
function BrokerRow({ broker: b, qc, onActivate, onRemove, activating }: {
  broker: any; qc: any;
  onActivate: () => void; onRemove: () => void; activating: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [token, setToken]       = useState("");
  const [showToken, setShow]    = useState(false);

  const deactivateMutation = useMutation({
    mutationFn: () => api.patch(`/brokers/${b.id}/deactivate`),
    onSuccess: () => { toast.success("Broker deactivated"); qc.invalidateQueries({queryKey:["brokers"]}); },
    onError: () => toast.error("Deactivation failed"),
  });

  const renewMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-renew"),
    onSuccess: (res: any) => {
      toast.success(`✅ Token renewed — expires ${res.data?.expires_at ?? "in 24h"}`);
      qc.invalidateQueries({queryKey:["settings-status"]});
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Renewal failed — token may be expired"),
  });

  const updateTokenMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-token", {access_token: token}),
    onSuccess: (res: any) => {
      toast.success(res.data?.valid ? "✅ Token updated & verified" : "Token saved");
      qc.invalidateQueries({queryKey:["settings-status","brokers"]});
      setToken(""); setExpanded(false);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Update failed"),
  });

  return (
    <div style={{borderTop:"1px solid var(--border)"}}>
      {/* Main row */}
      <div style={{
        padding:"16px 20px", display:"flex",
        alignItems:"center", justifyContent:"space-between",
      }}>
        <div style={{display:"flex", alignItems:"center", gap:14}}>
          <div style={{
            width:36, height:36, borderRadius:4,
            background:"rgba(0,255,136,0.1)", border:"1px solid rgba(0,255,136,0.3)",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:13, fontWeight:700, color:"var(--green)",
          }}>{b.broker[0].toUpperCase()}</div>
          <div>
            <div style={{fontWeight:700, fontSize:13}}>{b.broker.toUpperCase()}</div>
            <div style={{fontSize:11, color:"var(--muted)"}}>Client ID: {b.client_id}</div>
          </div>
        </div>

        <div style={{display:"flex", alignItems:"center", gap:8}}>
          <span className={`badge ${b.paper_trading?"badge-yellow":"badge-green"}`}>
            {b.paper_trading ? "PAPER" : "LIVE"}
          </span>
          <span className={`badge ${b.is_active?"badge-green":"badge-gray"}`}>
            {b.is_active ? "● ACTIVE" : "○ INACTIVE"}
          </span>

          {/* Activate / Deactivate */}
          {!b.is_active ? (
            <button className="connect-btn" style={{padding:"5px 12px", fontSize:10}}
              onClick={onActivate} disabled={activating}>
              {activating ? "..." : "⚡ ACTIVATE"}
            </button>
          ) : (
            <button className="exit-btn"
              style={{padding:"5px 12px", fontSize:10,
                color:"var(--yellow)", borderColor:"rgba(255,208,96,0.3)"}}
              onClick={() => deactivateMutation.mutate()}
              disabled={deactivateMutation.isPending}>
              {deactivateMutation.isPending ? "..." : "⏸ DEACTIVATE"}
            </button>
          )}

          {/* Edit token */}
          {!b.paper_trading && (
            <button
              onClick={() => setExpanded(v => !v)}
              style={{
                padding:"5px 12px", fontSize:10, cursor:"pointer",
                fontFamily:"var(--font)",
                background: expanded ? "rgba(0,255,136,0.1)" : "transparent",
                border: `1px solid ${expanded ? "rgba(0,255,136,0.4)" : "var(--border)"}`,
                color: expanded ? "var(--green)" : "var(--muted)",
              }}>
              {expanded ? "✕ CLOSE" : "✎ EDIT TOKEN"}
            </button>
          )}

          <button className="exit-btn" onClick={onRemove}>REMOVE</button>
        </div>
      </div>

      {/* Expanded token edit panel */}
      {expanded && !b.paper_trading && (
        <div style={{
          margin:"0 20px 16px",
          padding:"16px",
          background:"rgba(0,0,0,0.2)",
          border:"1px solid var(--border)",
        }}>
          <div style={{fontSize:11, color:"var(--muted)", marginBottom:12}}>
            Get new token from{" "}
            <a href="https://web.dhan.co" target="_blank" rel="noreferrer"
              style={{color:"var(--green)"}}>web.dhan.co</a>
            {" → My Profile → Access DhanHQ APIs → Generate Token"}
          </div>

          {/* Auto renew */}
          <div style={{marginBottom:12}}>
            <span style={{fontSize:11, color:"var(--muted)", marginRight:10}}>
              Token still active?
            </span>
            <button
              className={`connect-btn${renewMutation.isPending?" loading":""}`}
              onClick={() => renewMutation.mutate()}
              disabled={renewMutation.isPending}
              style={{fontSize:10, padding:"4px 12px"}}>
              {renewMutation.isPending ? "RENEWING..." : "⟳ AUTO RENEW (extends 24h)"}
            </button>
          </div>

          {/* Manual token paste */}
          <div style={{display:"flex", gap:8, alignItems:"center"}}>
            <div style={{position:"relative", flex:1}}>
              <input className="field-input"
                type={showToken ? "text" : "password"}
                value={token}
                onChange={e => setToken(e.target.value)}
                placeholder="Paste new token (eyJ...) — use when expired"
                style={{paddingRight:60, width:"100%"}} />
              <button onClick={() => setShow(v => !v)} style={{
                position:"absolute", right:10, top:"50%",
                transform:"translateY(-50%)", background:"transparent",
                border:"none", color:"var(--muted)", cursor:"pointer", fontSize:10,
              }}>{showToken ? "HIDE" : "SHOW"}</button>
            </div>
            <button
              className={`connect-btn${updateTokenMutation.isPending?" loading":""}`}
              onClick={() => updateTokenMutation.mutate()}
              disabled={!token.trim() || updateTokenMutation.isPending}
              style={{whiteSpace:"nowrap", fontSize:10}}>
              {updateTokenMutation.isPending ? "..." : "UPDATE →"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
