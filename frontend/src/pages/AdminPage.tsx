import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

export default function AdminPage() {
  const [tab, setTab] = useState<"overview"|"users"|"strategies"|"trades">("overview");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">ADMIN CONSOLE</h1>
          <p className="page-sub">Platform management & user control</p>
        </div>
      </div>
      <div className="tab-switcher" style={{ marginBottom:24 }}>
        {(["overview","users","strategies","trades"] as const).map(t => (
          <button key={t} className={`tab-btn${tab===t?" active":""}`} onClick={()=>setTab(t)}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>
      {tab==="overview"   && <OverviewTab />}
      {tab==="users"      && <UsersTab />}
      {tab==="strategies" && <StrategiesTab />}
      {tab==="trades"     && <TradesTab />}
    </Layout>
  );
}

/* ── OVERVIEW ─────────────────────────────────────────────── */
function OverviewTab() {
  const { data } = useQuery({
    queryKey:["admin-overview"],
    queryFn: ()=>api.get("/admin/overview").then(r=>r.data),
    refetchInterval:30_000,
  });
  if (!data) return <Spinner />;
  return (
    <div>
      <div className="stats-grid" style={{ marginBottom:24 }}>
        <StatCard label="TOTAL USERS"       value={data.users.total}              sub={`${data.users.active} active`} />
        <StatCard label="TOTAL TRADES"      value={data.trades.total}             sub={`${data.trades.live} live · ${data.trades.paper} paper`} />
        <StatCard label="ACTIVE STRATEGIES" value={data.strategies.active_assignments} sub={`${data.strategies.total} configured`} color="green" />
        <StatCard label="TOTAL SIGNALS"     value={data.signals.total}            sub="copy trade signals" />
      </div>
      <div className="info-box">
        <div className="info-icon">◉</div>
        <div>
          <div className="info-title">ADMIN PANEL</div>
          <div className="info-body">
            Manage users, assign strategies, view all trades platform-wide.
            Use the tabs above to navigate. Changes take effect immediately.
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── USERS ────────────────────────────────────────────────── */
function UsersTab() {
  const qc = useQueryClient();
  const { data: users, isLoading } = useQuery({
    queryKey:["admin-users"],
    queryFn: ()=>api.get("/admin/users").then(r=>r.data),
  });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ email:"", username:"", password:"", role:"trader" });
  const set = (k:string)=>(e:any)=>setForm(f=>({...f,[k]:e.target.value}));

  const createMutation = useMutation({
    mutationFn: ()=>api.post("/admin/users", form),
    onSuccess: ()=>{ toast.success("User created"); qc.invalidateQueries({queryKey:["admin-users"]}); setShowForm(false); },
    onError:(e:any)=>toast.error(e.response?.data?.detail||"Failed"),
  });
  const toggleMutation = useMutation({
    mutationFn:(id:string)=>api.patch(`/admin/users/${id}/toggle`),
    onSuccess:()=>qc.invalidateQueries({queryKey:["admin-users"]}),
  });
  const deleteMutation = useMutation({
    mutationFn:(id:string)=>api.delete(`/admin/users/${id}`),
    onSuccess:()=>{ toast.success("User deleted"); qc.invalidateQueries({queryKey:["admin-users"]}); },
  });

  if (isLoading) return <Spinner />;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">ALL USERS ({users?.length??0})</span>
        <button className="connect-btn" onClick={()=>setShowForm(v=>!v)}>
          {showForm?"✕ CANCEL":"+ CREATE USER"}
        </button>
      </div>

      {showForm && (
        <div style={{ padding:"20px", borderBottom:"1px solid var(--border)",
          display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
          <FormField label="EMAIL"    value={form.email}    onChange={set("email")}    type="email" />
          <FormField label="USERNAME" value={form.username} onChange={set("username")} type="text" />
          <FormField label="PASSWORD" value={form.password} onChange={set("password")} type="password" />
          <div className="field">
            <label className="field-label">ROLE</label>
            <select className="field-input" value={form.role} onChange={set("role")}
              style={{ background:"rgba(0,255,136,0.04)", color:"var(--text)", fontFamily:"var(--font)" }}>
              <option value="trader">Trader</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button className="auth-btn" onClick={()=>createMutation.mutate()}
            disabled={createMutation.isPending} style={{ gridColumn:"span 2", marginTop:4 }}>
            {createMutation.isPending?"CREATING...":"CREATE USER →"}
          </button>
        </div>
      )}

      <table className="data-table">
        <thead><tr>
          {["USERNAME","EMAIL","ROLE","STATUS","BROKERS","STRATEGIES","TRADES","ACTIONS"].map(h=><th key={h}>{h}</th>)}
        </tr></thead>
        <tbody>
          {users?.map((u:any)=>(
            <tr key={u.id}>
              <td className="symbol">{u.username}</td>
              <td style={{color:"var(--muted)",fontSize:11}}>{u.email}</td>
              <td><span className={`badge ${u.role==="admin"?"badge-yellow":"badge-gray"}`}>
                {u.role.toUpperCase()}
              </span></td>
              <td><span className={`badge ${u.is_active?"badge-green":"badge-gray"}`}>
                {u.is_active?"ACTIVE":"DISABLED"}
              </span></td>
              <td>{u.brokers}</td>
              <td>{u.strategies}</td>
              <td>{u.trades}</td>
              <td style={{display:"flex",gap:6}}>
                <button className="exit-btn" onClick={()=>toggleMutation.mutate(u.id)}>
                  {u.is_active?"DISABLE":"ENABLE"}
                </button>
                <button className="exit-btn"
                  style={{borderColor:"rgba(255,68,102,0.4)",color:"var(--red)"}}
                  onClick={()=>{ if(confirm(`Delete ${u.username}?`)) deleteMutation.mutate(u.id); }}>
                  DEL
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── STRATEGIES ───────────────────────────────────────────── */
function StrategiesTab() {
  const qc = useQueryClient();
  const { data:strats, isLoading } = useQuery({
    queryKey:["admin-strategies"],
    queryFn:()=>api.get("/admin/strategies").then(r=>r.data),
  });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name:"", description:"", engine_class:"", default_params:"{}" });
  const set=(k:string)=>(e:any)=>setForm(f=>({...f,[k]:e.target.value}));

  const createMutation = useMutation({
    mutationFn:()=>api.post("/admin/strategies",{
      ...form, default_params: JSON.parse(form.default_params||"{}")
    }),
    onSuccess:()=>{ toast.success("Strategy created"); qc.invalidateQueries({queryKey:["admin-strategies"]}); setShowForm(false); },
    onError:(e:any)=>toast.error(e.response?.data?.detail||"Failed"),
  });
  const toggleMutation = useMutation({
    mutationFn:(id:string)=>api.patch(`/admin/strategies/${id}/toggle`),
    onSuccess:()=>qc.invalidateQueries({queryKey:["admin-strategies"]}),
  });

  if (isLoading) return <Spinner />;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">STRATEGIES ({strats?.length??0})</span>
        <button className="connect-btn" onClick={()=>setShowForm(v=>!v)}>
          {showForm?"✕ CANCEL":"+ ADD STRATEGY"}
        </button>
      </div>

      {showForm && (
        <div style={{ padding:"20px", borderBottom:"1px solid var(--border)" }}>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12 }}>
            <FormField label="NAME"         value={form.name}         onChange={set("name")}         type="text" />
            <FormField label="ENGINE CLASS" value={form.engine_class} onChange={set("engine_class")} type="text" placeholder="moving_average_crossover" />
          </div>
          <FormField label="DESCRIPTION" value={form.description} onChange={set("description")} type="text" />
          <div className="field">
            <label className="field-label">DEFAULT PARAMS (JSON)</label>
            <textarea className="field-input" value={form.default_params}
              onChange={set("default_params")} rows={4}
              style={{ resize:"vertical", fontFamily:"var(--font)", fontSize:11 }} />
          </div>
          <button className="auth-btn" onClick={()=>createMutation.mutate()}
            disabled={createMutation.isPending}>
            {createMutation.isPending?"CREATING...":"CREATE STRATEGY →"}
          </button>
        </div>
      )}

      <table className="data-table">
        <thead><tr>{["NAME","ENGINE CLASS","STATUS","ACTIONS"].map(h=><th key={h}>{h}</th>)}</tr></thead>
        <tbody>
          {strats?.map((s:any)=>(
            <tr key={s.id}>
              <td className="symbol">{s.name}</td>
              <td style={{color:"var(--muted)",fontSize:11,fontFamily:"var(--font)"}}>{s.engine_class}</td>
              <td><span className={`badge ${s.is_available?"badge-green":"badge-gray"}`}>
                {s.is_available?"AVAILABLE":"HIDDEN"}
              </span></td>
              <td>
                <button className="exit-btn" onClick={()=>toggleMutation.mutate(s.id)}>
                  {s.is_available?"HIDE":"SHOW"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── TRADES ───────────────────────────────────────────────── */
function TradesTab() {
  const { data:trades, isLoading } = useQuery({
    queryKey:["admin-trades"],
    queryFn:()=>api.get("/admin/trades?limit=100").then(r=>r.data),
    refetchInterval:15_000,
  });

  if (isLoading) return <Spinner />;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">ALL TRADES</span>
        <span className="card-badge">{trades?.length??0} recent</span>
      </div>
      <table className="data-table">
        <thead><tr>
          {["USER","SYMBOL","DIR","QTY","ENTRY","P&L","STATUS","MODE","TIME"].map(h=><th key={h}>{h}</th>)}
        </tr></thead>
        <tbody>
          {trades?.map((t:any)=>(
            <tr key={t.id}>
              <td style={{color:"var(--muted)",fontSize:10}}>{t.user_id?.slice(0,8)}…</td>
              <td className="symbol">{t.symbol}</td>
              <td><span className={`badge ${t.direction==="BUY"?"badge-green":"badge-red"}`}>{t.direction}</span></td>
              <td>{t.quantity}</td>
              <td>{t.entry_price?`₹${t.entry_price.toLocaleString()}`:"—"}</td>
              <td className={t.pnl==null?"":t.pnl>=0?"pnl-pos":"pnl-neg"}>
                {t.pnl==null?"—":`${t.pnl>=0?"+":""}₹${t.pnl.toLocaleString()}`}
              </td>
              <td><span className={`badge ${t.status==="CLOSED"?"badge-gray":t.status==="OPEN"?"badge-green":"badge-yellow"}`}>
                {t.status}
              </span></td>
              <td><span className={`badge ${t.is_paper?"badge-yellow":"badge-red"}`}>
                {t.is_paper?"PAPER":"LIVE"}
              </span></td>
              <td style={{color:"var(--muted)",fontSize:10}}>
                {t.created_at?new Date(t.created_at).toLocaleTimeString():"—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Helpers ──────────────────────────────────────────────── */
function StatCard({label,value,sub,color}:any) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{color:color==="green"?"var(--green)":color==="red"?"var(--red)":"var(--text)"}}>
        {value}
      </div>
      {sub && <div className="stat-delta neu">{sub}</div>}
    </div>
  );
}
function FormField({label,value,onChange,type,placeholder}:any) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input className="field-input" type={type} value={value} onChange={onChange} placeholder={placeholder} />
    </div>
  );
}
function Spinner() {
  return <div style={{color:"var(--muted)",padding:20,fontSize:12}}>Loading...</div>;
}
