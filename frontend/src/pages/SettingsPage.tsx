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
      <div className="settings-board">
        <PasswordCard />
        <BrokerSettingsSection />
        {isAdmin && <TokenRenewalCard qc={qc} />}
      </div>
    </Layout>
  );
}

function TokenRenewalCard({qc}: {qc: any}) {
  const [newToken, setNewToken] = useState("");
  const [showToken, setShow]    = useState(false);
  const { data } = useQuery({
    queryKey: ["settings-status"],
    queryFn: () => api.get("/settings/status").then(r => r.data),
    refetchInterval: 60_000,
  });
  const dhan = data?.dhan ?? {};

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
    <div className="card settings-card">
      <div className="card-header">
        <span className="card-title">DHAN TOKEN</span>
        <span className={`badge ${dhan.token_valid ? "badge-green" : "badge-red"}`}>
          {dhan.token_valid ? "CONNECTED" : "NEEDS TOKEN"}
        </span>
      </div>
      <div className="token-grid">
        <div>
          <div className="field-label">CLIENT ID</div>
          <div className="token-value">{dhan.client_id_set ? "Saved" : "Missing"}</div>
        </div>
        <div>
          <div className="field-label">ACCESS TOKEN</div>
          <div className="token-value">{dhan.token_set ? (dhan.token_valid ? "Active" : "Expired") : "Missing"}</div>
        </div>
        <div>
          <div className="field-label">AUTO RENEW</div>
          <div className="token-value">7:45 IST</div>
        </div>
        <button className="connect-btn" onClick={() => renewMutation.mutate()} disabled={renewMutation.isPending}>
          {renewMutation.isPending ? "RENEWING" : "RENEW 24H"}
        </button>
      </div>
      <div className="token-update">
        <input className="field-input" type={showToken ? "text" : "password"} value={newToken}
          onChange={e => setNewToken(e.target.value)} placeholder="Paste a new access token" />
        <button type="button" className="connect-btn" onClick={() => setShow(v => !v)}>{showToken ? "HIDE" : "SHOW"}</button>
        <button className="connect-btn" onClick={() => updateMutation.mutate()} disabled={!newToken.trim() || updateMutation.isPending}>
          {updateMutation.isPending ? "SAVING" : "SAVE"}
        </button>
      </div>
      <p className="token-note">
        Generate a token at <a href="https://web.dhan.co" target="_blank" rel="noreferrer">web.dhan.co</a>.
        Renewal runs at 7:45, instruments at 8:00, and risk limits reset at 9:15 IST.
      </p>
    </div>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const mutation = useMutation({
    mutationFn: () => api.post("/users/me/change-password", {
      current_password: current,
      new_password: next,
    }),
    onSuccess: () => {
      toast.success("Password updated");
      setCurrent("");
      setNext("");
      setConfirm("");
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Could not change password"),
  });

  function submit() {
    if (next.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    if (next !== confirm) {
      toast.error("New passwords do not match");
      return;
    }
    mutation.mutate();
  }

  return (
    <div className="card settings-card">
      <div className="card-header">
        <span className="card-title">PASSWORD</span>
      </div>
      <div style={{padding:"16px 20px", display:"grid", gap:12}}>
        <div className="field">
          <label className="field-label">CURRENT PASSWORD</label>
          <input className="field-input" type="password" value={current} onChange={e => setCurrent(e.target.value)} />
        </div>
        <div className="field">
          <label className="field-label">NEW PASSWORD</label>
          <input className="field-input" type="password" value={next} onChange={e => setNext(e.target.value)} />
        </div>
        <div className="field">
          <label className="field-label">CONFIRM NEW PASSWORD</label>
          <input className="field-input" type="password" value={confirm} onChange={e => setConfirm(e.target.value)} />
        </div>
        <button className="connect-btn" style={{justifySelf:"start"}} onClick={submit} disabled={mutation.isPending}>
          {mutation.isPending ? "SAVING" : "UPDATE PASSWORD"}
        </button>
        <p className="token-note">
          This needs the current password. If it is forgotten, an admin can set a new one from Console → Users → Reset.
        </p>
      </div>
    </div>
  );
}

// ── Broker Settings Section ───────────────────────────────────────────────────
function BrokerSettingsSection() {
  const qc = useQueryClient();
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
    <div className="card settings-card">
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
  );
}

function BrokerRow({ broker: b, onRemove, onDeactivate }: any) {

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
          <button className="exit-btn" onClick={onRemove}>REMOVE</button>
        </div>
      </div>
    </div>
  );
}
