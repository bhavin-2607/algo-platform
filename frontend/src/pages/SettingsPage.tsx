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
          <p className="page-sub">Platform configuration & broker credentials</p>
        </div>
      </div>
      <div style={{display:"flex", flexDirection:"column", gap:16, maxWidth:720}}>
        {isAdmin ? (
          <>
            <PlatformStatus />
            <DhanCredentialsCard qc={qc} />
            <TokenRenewalCard qc={qc} />
          </>
        ) : (
          <div className="card">
            <div style={{padding:24, color:"var(--muted)", textAlign:"center"}}>
              Settings are available to admin users only.
            </div>
          </div>
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
