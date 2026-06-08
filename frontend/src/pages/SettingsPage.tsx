import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

export default function SettingsPage() {
  const { user } = useAuthStore();
  const isAdmin  = user?.role === "admin";
  const qc       = useQueryClient();

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">SETTINGS</h1>
          <p className="page-sub">Account configuration & broker connections</p>
        </div>
      </div>
      <div style={{display:"flex", flexDirection:"column", gap:16, maxWidth:720}}>
        <BrokerSettingsSection />
        {isAdmin && (
          <>
            <PlatformStatus />
            <DhanCredentialsCard qc={qc} />
            <TokenRenewalCard qc={qc} />
          </>
        )}
      </div>
    </Layout>
  );
}

function PlatformStatus() {
  const { data } = useQuery({
    queryKey: ["settings-status"],
    queryFn: () => api.get("/settings/status").then(r => r.data),
    refetchInterval: 60_000,
  });
  const dhan = data?.dhan ?? {};
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">PLATFORM STATUS</span>
        <span className={`badge ${dhan.token_valid ? "badge-green" : "badge-red"}`}>
          {dhan.token_valid ? "● CONNECTED" : "○ DISCONNECTED"}
        </span>
      </div>
      <div style={{padding:"16px 20px", display:"flex", gap:32, flexWrap:"wrap"}}>
        {[
          {label:"CLIENT ID",    value:dhan.client_id_set?"✓ Set":"✗ Not set",    ok:dhan.client_id_set},
          {label:"ACCESS TOKEN", value:dhan.token_set?"✓ Set":"✗ Not set",        ok:dhan.token_set},
          {label:"TOKEN VALID",  value:dhan.token_valid?"✓ Active":"✗ Expired",   ok:dhan.token_valid},
          {label:"AUTO-RENEWAL", value:"7:45 AM IST daily",                         ok:true},
        ].map(({label,value,ok}) => (
          <div key={label}>
            <div style={{fontSize:9,letterSpacing:2,color:"var(--muted)",marginBottom:4}}>{label}</div>
            <div style={{fontSize:13,fontWeight:700,color:ok?"var(--green)":"var(--red)"}}>{value}</div>
          </div>
        ))}
      </div>
      {dhan.alert === "RENEWAL_FAILED" && (
        <div style={{margin:"0 20px 16px",padding:"10px 14px",
          background:"rgba(255,68,102,0.1)",border:"1px solid rgba(255,68,102,0.3)",
          fontSize:12,color:"var(--red)"}}>
          ⚠ Automated token renewal failed. Update your token below.
        </div>
      )}
    </div>
  );
}

function DhanCredentialsCard({qc}: {qc: any}) {
  const [form, setForm]       = useState({client_id:"", access_token:""});
  const [showToken, setShow]  = useState(false);
  const set = (k: string) => (e: any) => setForm(f => ({...f, [k]:e.target.value}));

  const {data: current} = useQuery({
    queryKey: ["dhan-credentials"],
    queryFn: () => api.get("/settings/dhan-credentials").then(r => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-credentials", form),
    onSuccess: () => {
      toast.success("✅ Credentials updated & verified");
      qc.invalidateQueries({queryKey:["settings-status"]});
      qc.invalidateQueries({queryKey:["dhan-credentials"]});
      setForm({client_id:"", access_token:""});
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Update failed"),
  });

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">DHAN CREDENTIALS</span>
        {current?.client_id && (
          <span style={{fontSize:11,color:"var(--muted)"}}>
            ID: {current.client_id} · Token: {current.token_preview}
          </span>
        )}
      </div>
      <div style={{padding:"16px 20px 20px"}}>
        <p style={{fontSize:12,color:"var(--muted)",marginBottom:16}}>
          Generate at{" "}
          <a href="https://web.dhan.co" target="_blank" rel="noreferrer"
            style={{color:"var(--green)"}}>web.dhan.co</a>
          {" → My Profile → Access DhanHQ APIs → Generate Token"}
        </p>
        <div style={{display:"flex",flexDirection:"column",gap:12}}>
          <div className="field">
            <label className="field-label">DHAN CLIENT ID</label>
            <input className="field-input" value={form.client_id}
              onChange={set("client_id")}
              placeholder={current?.client_id || "Your Dhan Client ID"} />
          </div>
          <div className="field">
            <label className="field-label">ACCESS TOKEN</label>
            <div style={{position:"relative"}}>
              <input className="field-input"
                type={showToken?"text":"password"}
                value={form.access_token}
                onChange={set("access_token")}
                placeholder="Paste your access token (eyJ...)"
                style={{paddingRight:60,width:"100%"}} />
              <button onClick={()=>setShow(v=>!v)} style={{
                position:"absolute",right:10,top:"50%",transform:"translateY(-50%)",
                background:"transparent",border:"none",color:"var(--muted)",
                cursor:"pointer",fontSize:11}}>
                {showToken?"HIDE":"SHOW"}
              </button>
            </div>
          </div>
          <button
            className={`auth-btn${saveMutation.isPending?" loading":""}`}
            onClick={()=>saveMutation.mutate()}
            disabled={!form.client_id||!form.access_token||saveMutation.isPending}
            style={{maxWidth:200,marginTop:4}}>
            {saveMutation.isPending?"VERIFYING...":"SAVE & VERIFY →"}
          </button>
        </div>
      </div>
    </div>
  );
}

function TokenRenewalCard({qc}: {qc: any}) {
  const [newToken, setNewToken] = useState("");
  const [showToken, setShow]    = useState(false);

  const updateMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-token", {access_token: newToken}),
    onSuccess: (res: any) => {
      toast.success(res.data?.valid ? "✅ Token updated & verified" : "Token saved (verify failed)");
      qc.invalidateQueries({queryKey:["settings-status"]});
      qc.invalidateQueries({queryKey:["dhan-credentials"]});
      setNewToken("");
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Update failed"),
  });

  const renewMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-renew"),
    onSuccess: (res: any) => {
      toast.success(`✅ Token renewed — expires ${res.data?.expires_at ?? "in 24h"}`);
      qc.invalidateQueries({queryKey:["settings-status"]});
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Renewal failed"),
  });

  return (
    <div className="card">
      <div className="card-header"><span className="card-title">TOKEN MANAGEMENT</span></div>
      <div style={{padding:"16px 20px 20px",display:"flex",flexDirection:"column",gap:16}}>

        {/* Auto renew */}
        <div style={{padding:"14px 16px",
          background:"rgba(0,255,136,0.04)",border:"1px solid rgba(0,255,136,0.15)"}}>
          <div style={{fontSize:12,fontWeight:700,marginBottom:6}}>AUTO RENEW</div>
          <div style={{fontSize:11,color:"var(--muted)",marginBottom:12}}>
            Extends current active token by 24h. Only works if token is still valid.
            Celery Beat runs this automatically at 7:45 AM IST.
          </div>
          <button className={`connect-btn${renewMutation.isPending?" loading":""}`}
            onClick={()=>renewMutation.mutate()}
            disabled={renewMutation.isPending} style={{fontSize:11}}>
            {renewMutation.isPending?"RENEWING...":"⟳ RENEW TOKEN NOW"}
          </button>
        </div>

        {/* Manual paste */}
        <div style={{padding:"14px 16px",
          background:"rgba(255,208,96,0.04)",border:"1px solid rgba(255,208,96,0.15)"}}>
          <div style={{fontSize:12,fontWeight:700,color:"var(--yellow)",marginBottom:6}}>
            MANUAL TOKEN UPDATE
          </div>
          <div style={{fontSize:11,color:"var(--muted)",marginBottom:12}}>
            Use when token is expired & auto-renew fails. Generate at{" "}
            <a href="https://web.dhan.co" target="_blank" rel="noreferrer"
              style={{color:"var(--green)"}}>web.dhan.co</a>
            {" → My Profile → Access DhanHQ APIs"}
          </div>
          <div style={{display:"flex",gap:8}}>
            <div style={{position:"relative",flex:1}}>
              <input className="field-input"
                type={showToken?"text":"password"}
                value={newToken}
                onChange={e=>setNewToken(e.target.value)}
                placeholder="Paste new access token (eyJ...)"
                style={{paddingRight:60,width:"100%"}} />
              <button onClick={()=>setShow(v=>!v)} style={{
                position:"absolute",right:10,top:"50%",transform:"translateY(-50%)",
                background:"transparent",border:"none",
                color:"var(--muted)",cursor:"pointer",fontSize:11}}>
                {showToken?"HIDE":"SHOW"}
              </button>
            </div>
            <button className={`connect-btn${updateMutation.isPending?" loading":""}`}
              onClick={()=>updateMutation.mutate()}
              disabled={!newToken.trim()||updateMutation.isPending}
              style={{whiteSpace:"nowrap",fontSize:11}}>
              {updateMutation.isPending?"...":"UPDATE →"}
            </button>
          </div>
        </div>

        {/* Schedule */}
        <div style={{fontSize:11,color:"var(--muted)"}}>
          <div style={{fontWeight:700,marginBottom:6,color:"var(--text)"}}>CELERY BEAT SCHEDULE</div>
          {[
            ["7:45 AM","Token renewal (RenewToken API)"],
            ["8:00 AM","Instrument CSV refresh"],
            ["9:15 AM","Daily risk limits reset"],
          ].map(([time,desc])=>(
            <div key={time} style={{display:"flex",gap:16,marginBottom:4}}>
              <span style={{color:"var(--green)",minWidth:60}}>{time} IST</span>
              <span>{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Broker Settings Section ───────────────────────────────────────────────────
function BrokerSettingsSection() {
  const qc = useQueryClient();
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ broker:"dhan", client_id:"", access_token:"", paper_trading:false });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  const connectMutation = useMutation({
    mutationFn: () => api.post("/brokers", {
      broker: form.broker, client_id: form.client_id,
      paper_trading: form.paper_trading,
    }).then(async (res) => {
      if (!form.paper_trading && form.access_token && form.client_id) {
        await api.post("/settings/dhan-credentials", {
          client_id: form.client_id, access_token: form.access_token,
        });
      }
      return res;
    }),
    onSuccess: () => { toast.success("Broker added"); qc.invalidateQueries({queryKey:["brokers"]}); setShowForm(false); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed"),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/brokers/${id}`),
    onSuccess: () => { toast.success("Removed"); qc.invalidateQueries({queryKey:["brokers"]}); },
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => api.patch(`/brokers/${id}/deactivate`),
    onSuccess: () => { toast.success("Deactivated"); qc.invalidateQueries({queryKey:["brokers"]}); },
  });

  const visibleBrokers = (brokers ?? []).filter((b: any) => b.broker !== "shoonya");

  return (
    <div style={{display:"flex", flexDirection:"column", gap:16, maxWidth:720}}>
      {/* Connected Brokers */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">CONNECTED BROKERS</span>
          <button className="connect-btn" onClick={() => setShowForm(v=>!v)}>
            {showForm ? "✕ CANCEL" : "+ ADD BROKER"}
          </button>
        </div>

        {showForm && (
          <div style={{padding:"20px 20px 0"}}>
            <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12}}>
              <div className="field">
                <label className="field-label">CLIENT ID</label>
                <input className="field-input" value={form.client_id}
                  onChange={e=>setForm(f=>({...f, client_id:e.target.value}))}
                  placeholder="Your Dhan Client ID" />
              </div>
              <div className="field">
                <label className="field-label">MODE</label>
                <div style={{display:"flex"}}>
                  {["Paper","Live"].map((m,i)=>(
                    <button key={m} type="button"
                      onClick={()=>setForm(f=>({...f, paper_trading:m==="Paper"}))}
                      style={{
                        flex:1, padding:11, fontFamily:"var(--font)", fontSize:11,
                        cursor:"pointer", border:"1px solid",
                        borderRight:i===0?"none":undefined,
                        background:(form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                          ? m==="Paper"?"rgba(255,208,96,0.15)":"rgba(255,68,102,0.1)" : "transparent",
                        borderColor:(form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                          ? m==="Paper"?"rgba(255,208,96,0.4)":"rgba(255,68,102,0.4)" : "var(--border)",
                        color:(form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                          ? m==="Paper"?"var(--yellow)":"var(--red)" : "var(--muted)",
                      }}>{m.toUpperCase()}</button>
                  ))}
                </div>
              </div>
            </div>
            {!form.paper_trading && (
              <div className="field" style={{marginBottom:12}}>
                <label className="field-label">ACCESS TOKEN</label>
                <input className="field-input" type="password"
                  value={form.access_token}
                  onChange={e=>setForm(f=>({...f, access_token:e.target.value}))}
                  placeholder="Paste access token (eyJ...)" />
              </div>
            )}
            <button className={`auth-btn${connectMutation.isPending?" loading":""}`}
              onClick={()=>connectMutation.mutate()}
              disabled={connectMutation.isPending}
              style={{maxWidth:200, marginBottom:20}}>
              {connectMutation.isPending?"ADDING...":"ADD BROKER →"}
            </button>
          </div>
        )}

        {visibleBrokers.length === 0 && !showForm && (
          <div style={{padding:"30px 20px", textAlign:"center", color:"var(--muted)", fontSize:12}}>
            No broker connected. Add Dhan to start trading.
          </div>
        )}

        {visibleBrokers.map((b: any) => (
          <BrokerRow key={b.id} broker={b} qc={qc}
            onRemove={()=>removeMutation.mutate(b.id)}
            onDeactivate={()=>deactivateMutation.mutate(b.id)}
          />
        ))}
      </div>

      {/* Token Management — admin only */}
      {isAdmin && <TokenRenewalCard qc={qc} />}
    </div>
  );
}

function BrokerRow({ broker: b, qc, onRemove, onDeactivate }: any) {
  const [expanded, setExpanded] = useState(false);
  const [token, setToken]       = useState("");
  const [show, setShow]         = useState(false);

  const renewMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-renew"),
    onSuccess: (res: any) => { toast.success(`✅ Renewed — expires ${res.data?.expires_at ?? "24h"}`); qc.invalidateQueries({queryKey:["settings-status"]}); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Renewal failed"),
  });

  const updateMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-token", {access_token: token}),
    onSuccess: () => { toast.success("✅ Token updated"); qc.invalidateQueries({queryKey:["settings-status"]}); setToken(""); setExpanded(false); },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed"),
  });

  return (
    <div style={{borderTop:"1px solid var(--border)"}}>
      <div style={{padding:"16px 20px", display:"flex", alignItems:"center", justifyContent:"space-between"}}>
        <div style={{display:"flex", alignItems:"center", gap:14}}>
          <div style={{width:36, height:36, borderRadius:4,
            background:"rgba(0,255,136,0.1)", border:"1px solid rgba(0,255,136,0.3)",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:13, fontWeight:700, color:"var(--green)"}}>
            {b.broker[0].toUpperCase()}
          </div>
          <div>
            <div style={{fontWeight:700, fontSize:13}}>{b.broker.toUpperCase()}</div>
            <div style={{fontSize:11, color:"var(--muted)"}}>Client ID: {b.client_id}</div>
          </div>
        </div>
        <div style={{display:"flex", alignItems:"center", gap:8}}>
          <span className={`badge ${b.paper_trading?"badge-yellow":"badge-green"}`}>
            {b.paper_trading?"PAPER":"LIVE"}
          </span>
          <span className={`badge ${b.is_active?"badge-green":"badge-gray"}`}>
            {b.is_active?"● ACTIVE":"○ INACTIVE"}
          </span>
          {b.is_active && (
            <button className="exit-btn"
              style={{padding:"5px 12px", fontSize:10, color:"var(--yellow)", borderColor:"rgba(255,208,96,0.3)"}}
              onClick={onDeactivate}>⏸ DEACTIVATE</button>
          )}
          {!b.paper_trading && (
            <button onClick={()=>setExpanded(v=>!v)} style={{
              padding:"5px 12px", fontSize:10, cursor:"pointer", fontFamily:"var(--font)",
              background:expanded?"rgba(0,255,136,0.1)":"transparent",
              border:`1px solid ${expanded?"rgba(0,255,136,0.4)":"var(--border)"}`,
              color:expanded?"var(--green)":"var(--muted)"}}>
              {expanded?"✕ CLOSE":"✎ EDIT TOKEN"}
            </button>
          )}
          <button className="exit-btn" onClick={onRemove}>REMOVE</button>
        </div>
      </div>

      {expanded && (
        <div style={{margin:"0 20px 16px", padding:"16px",
          background:"rgba(0,0,0,0.2)", border:"1px solid var(--border)"}}>
          <div style={{fontSize:11, color:"var(--muted)", marginBottom:10}}>
            Get token from <a href="https://web.dhan.co" target="_blank" rel="noreferrer"
              style={{color:"var(--green)"}}>web.dhan.co</a> → My Profile → Access DhanHQ APIs
          </div>
          <div style={{marginBottom:10}}>
            <button className={`connect-btn${renewMutation.isPending?" loading":""}`}
              onClick={()=>renewMutation.mutate()} disabled={renewMutation.isPending}
              style={{fontSize:10}}>
              {renewMutation.isPending?"RENEWING...":"⟳ AUTO RENEW (extends 24h)"}
            </button>
          </div>
          <div style={{display:"flex", gap:8}}>
            <div style={{position:"relative", flex:1}}>
              <input className="field-input" type={show?"text":"password"}
                value={token} onChange={e=>setToken(e.target.value)}
                placeholder="Paste new token (eyJ...)"
                style={{paddingRight:60, width:"100%"}} />
              <button onClick={()=>setShow(v=>!v)} style={{
                position:"absolute", right:10, top:"50%", transform:"translateY(-50%)",
                background:"transparent", border:"none", color:"var(--muted)",
                cursor:"pointer", fontSize:10}}>{show?"HIDE":"SHOW"}</button>
            </div>
            <button className={`connect-btn${updateMutation.isPending?" loading":""}`}
              onClick={()=>updateMutation.mutate()}
              disabled={!token.trim()||updateMutation.isPending}
              style={{whiteSpace:"nowrap", fontSize:10}}>
              {updateMutation.isPending?"...":"UPDATE →"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
