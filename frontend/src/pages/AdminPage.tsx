import { Fragment, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

export default function AdminPage() {
  const [tab, setTab] = useState<"overview"|"users"|"trades"|"ip-whitelisting">("overview");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">ADMIN CONSOLE</h1>
          <p className="page-sub">Platform management, user control & Dhan security</p>
        </div>
      </div>
      <div className="tab-switcher" style={{ marginBottom:24 }}>
        {(["overview","users","trades","ip-whitelisting"] as const).map(t => (
          <button key={t} className={`tab-btn${tab===t?" active":""}`} onClick={()=>setTab(t)}>
            {t === "ip-whitelisting" ? "IP WHITELISTING" : t.toUpperCase()}
          </button>
        ))}
      </div>
      {tab==="overview"         && <OverviewTab />}
      {tab==="users"            && <UsersTab />}
      {tab==="trades"           && <TradesTab />}
      {tab==="ip-whitelisting"  && <IpWhitelistingTab />}
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
        <StatCard label="TOTAL USERS"         value={data.users?.total ?? 0}   sub={`${data.users?.active ?? 0} active`} />
        <StatCard label="TOTAL TRADES"        value={data.trades?.total ?? 0}  sub={`${data.trades?.live ?? 0} live · ${data.trades?.paper ?? 0} paper`} />
        <StatCard label="ALGO SCRIPTS"        value={data.algo?.total ?? 0}    sub={`${data.algo?.active ?? 0} automated active`} color="green" />
        <StatCard label="SERVER PUBLIC IP"    value={data.server_ip || "—"}   sub="outbound IPv4" color="cyan" />
      </div>
      <div className="info-box">
        <div className="info-icon">◉</div>
        <div>
          <div className="info-title">ADMINISTRATOR CONTROL PANEL</div>
          <div className="info-body">
            Manage platform users, verify trades, and configure Dhan IP Whitelisting directly using API access tokens.
            Use the tabs above to navigate.
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
  const [resetId, setResetId] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState("");
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
  const resetMutation = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      api.patch(`/admin/users/${id}/password`, { password }),
    onSuccess: () => {
      toast.success("Password reset");
      setResetId(null);
      setResetPassword("");
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Reset failed"),
  });

  if (isLoading) return <Spinner />;

  return (
    <div>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
        <span style={{ fontSize:13, color:"var(--muted)" }}>{users?.length??0} registered accounts</span>
        <button className="connect-btn" onClick={()=>setShowForm(v=>!v)}>
          {showForm ? "CANCEL" : "+ CREATE USER"}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ padding:20, marginBottom:20 }}>
          <div className="card-title" style={{ marginBottom:16 }}>NEW USER</div>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12 }}>
            <FormField label="EMAIL"    value={form.email}    onChange={set("email")}    type="email" />
            <FormField label="USERNAME" value={form.username} onChange={set("username")} type="text" />
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:16 }}>
            <FormField label="PASSWORD" value={form.password} onChange={set("password")} type="password" />
            <div className="field">
              <label className="field-label">ROLE</label>
              <select className="field-input" value={form.role} onChange={set("role")}
                style={{ background:"var(--surface)", color:"var(--text)", fontFamily:"var(--font)" }}>
                <option value="trader">Trader</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <button className="auth-btn" onClick={()=>createMutation.mutate()} disabled={createMutation.isPending}
            style={{ maxWidth:200 }}>
            {createMutation.isPending ? "CREATING..." : "CREATE USER →"}
          </button>
        </div>
      )}

      <div className="card">
        <table className="data-table">
          <thead><tr>
            {["USERNAME","EMAIL","ROLE","STATUS","BROKERS","TRADES","CREATED","ACTIONS"].map(h=><th key={h}>{h}</th>)}
          </tr></thead>
          <tbody>
            {users?.map((u:any)=>(
              <Fragment key={u.id}>
                <tr>
                  <td className="symbol">{u.username}</td>
                  <td style={{color:"var(--muted)"}}>{u.email}</td>
                  <td><span className={`badge ${u.role==="admin"?"badge-red":"badge-gray"}`}>{u.role.toUpperCase()}</span></td>
                  <td><span className={`badge ${u.is_active?"badge-green":"badge-red"}`}>{u.is_active?"ACTIVE":"SUSPENDED"}</span></td>
                  <td>{u.brokers}</td>
                  <td>{u.trades}</td>
                  <td style={{color:"var(--muted)",fontSize:11}}>{u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}</td>
                  <td style={{display:"flex", gap:6}}>
                    <button className="connect-btn" style={{padding:"2px 8px", fontSize:10}}
                      onClick={()=>setResetId(resetId===u.id?null:u.id)}>
                      {resetId===u.id ? "CANCEL" : "RESET PW"}
                    </button>
                    <button className="exit-btn" onClick={()=>toggleMutation.mutate(u.id)}>
                      {u.is_active ? "SUSPEND" : "ACTIVATE"}
                    </button>
                    <button className="exit-btn" style={{color:"var(--red)", borderColor:"rgba(255,68,102,0.3)"}}
                      onClick={()=>{ if(confirm(`Delete ${u.username}?`)) deleteMutation.mutate(u.id); }}>
                      DELETE
                    </button>
                  </td>
                </tr>
                {resetId===u.id && (
                  <tr key={u.id+"-reset"}>
                    <td colSpan={8} style={{padding:"12px 16px", background:"rgba(255,200,0,0.05)", borderTop:"1px solid var(--border)"}}>
                      <div style={{display:"flex", gap:10, alignItems:"center"}}>
                        <input className="field-input" type="password" placeholder="New password (min 8 chars)"
                          value={resetPassword} onChange={e=>setResetPassword(e.target.value)}
                          style={{maxWidth:300}} />
                        <button className="auth-btn" style={{maxWidth:160, margin:0}}
                          disabled={resetPassword.length<8||resetMutation.isPending}
                          onClick={()=>resetMutation.mutate({id:u.id, password:resetPassword})}>
                          {resetMutation.isPending?"SAVING...":"SAVE PASSWORD"}
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── IP WHITELISTING & VERIFICATION ────────────────────────── */
function IpWhitelistingTab() {
  const qc = useQueryClient();
  const [customIp, setCustomIp] = useState("");
  const [ipFlag, setIpFlag] = useState<"PRIMARY" | "SECONDARY">("PRIMARY");

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["admin-dhan-ip"],
    queryFn: () => api.get("/admin/dhan-ip").then((r) => r.data),
    staleTime: 5000,
  });

  const whitelistMutation = useMutation({
    mutationFn: (payload: { ip?: string; ip_flag?: string }) =>
      api.post("/admin/dhan-ip/whitelist", payload),
    onSuccess: (res: any) => {
      toast.success(res.data?.message || "IP whitelisted on Dhan successfully");
      qc.invalidateQueries({ queryKey: ["admin-dhan-ip"] });
      setCustomIp("");
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to whitelist IP on Dhan");
    },
  });

  if (isLoading) return <Spinner />;

  const isMatched = Boolean(data?.is_matched);
  const ordersAllowed = data?.orders_allowed;
  const serverIp = data?.current_server_ip || "Detecting...";
  const dhanDetectedIp = data?.dhan_detected_ip;
  const primaryIp = data?.dhan_primary_ip || "Not Set";
  const secondaryIp = data?.dhan_secondary_ip || "Not Set";
  const accountName = data?.account_name || data?.client_id || "Dhan";
  const eligibleDate = data?.modify_eligible_date;
  const modifyDatePrimary = data?.modify_date_primary;
  const modifyDateSecondary = data?.modify_date_secondary;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Verification Status Card */}
      <div className="card" style={{ padding: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", letterSpacing: 1 }}>
              DHAN STATIC IP VERIFICATION & WHITELISTING
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
              SEBI requires a registered static IP for automated order placement (error code DH-905 prevention).
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {ordersAllowed != null && (
              <span
                className={`badge ${ordersAllowed ? "badge-green" : "badge-red"}`}
                style={{ fontSize: 11, fontWeight: 700, padding: "4px 10px" }}
              >
                {ordersAllowed ? "ORDERS PERMITTED" : "ORDERS BLOCKED (IP MISMATCH)"}
              </span>
            )}
            <span
              className={`badge ${isMatched ? "badge-green" : "badge-red"}`}
              style={{ fontSize: 11, fontWeight: 700, padding: "4px 10px" }}
            >
              {isMatched ? "IP MATCHED" : "IP MISMATCH"}
            </span>
            <button
              type="button"
              className="connect-btn"
              onClick={() => refetch()}
              disabled={isFetching}
              style={{ fontSize: 10, padding: "4px 10px" }}
            >
              {isFetching ? "VERIFYING..." : "RE-VERIFY IP"}
            </button>
          </div>
        </div>

        {/* IP Comparison Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14, marginTop: 20 }}>
          <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", padding: "14px 16px", borderRadius: 4 }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1.2 }}>CURRENT PLATFORM SERVER IP</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: isMatched ? "var(--green)" : "var(--yellow)", marginTop: 6, wordBreak: "break-all" }}>
              {serverIp}
            </div>
            {dhanDetectedIp && (
              <div style={{ fontSize: 11, color: "#38bdf8", marginTop: 6, wordBreak: "break-all" }}>
                Dhan Detected: <strong>{dhanDetectedIp}</strong>
              </div>
            )}
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
              Outgoing address making Dhan API requests
            </div>
          </div>

          <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", padding: "14px 16px", borderRadius: 4 }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1.2 }}>DHAN REGISTERED PRIMARY IP</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: (primaryIp === serverIp || primaryIp === dhanDetectedIp) ? "var(--green)" : "var(--text)", marginTop: 6, wordBreak: "break-all" }}>
              {primaryIp}
            </div>
            {modifyDatePrimary && (
              <div style={{ fontSize: 10, color: "var(--yellow)", marginTop: 4 }}>
                Lock until: <strong>{modifyDatePrimary}</strong>
              </div>
            )}
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
              Account: {accountName}
            </div>
          </div>

          <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", padding: "14px 16px", borderRadius: 4 }}>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1.2 }}>DHAN REGISTERED SECONDARY IP</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: (secondaryIp === serverIp || secondaryIp === dhanDetectedIp) ? "var(--green)" : "var(--text)", marginTop: 6, wordBreak: "break-all" }}>
              {secondaryIp}
            </div>
            {modifyDateSecondary && (
              <div style={{ fontSize: 10, color: "var(--yellow)", marginTop: 4 }}>
                Lock until: <strong>{modifyDateSecondary}</strong>
              </div>
            )}
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
              Backup whitelisted IP
            </div>
          </div>
        </div>

        {eligibleDate && (
          <div style={{ marginTop: 14, fontSize: 11, color: "var(--yellow)" }}>
            Next eligible IP modification date: <strong>{eligibleDate}</strong>
          </div>
        )}
      </div>

      {/* 1-Click Action & Custom Whitelist Card */}
      <div className="card" style={{ padding: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--green)", letterSpacing: 1, marginBottom: 8 }}>
          WHITELIST IP DIRECTLY ON DHAN
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 18 }}>
          Updates the registered static IP on Dhan via the API using your active access token. Note that exchange rules apply a 7-day lock-in period after modifying an IP.
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Quick 1-click whitelist buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            {dhanDetectedIp && dhanDetectedIp !== serverIp ? (
              <>
                <button
                  type="button"
                  disabled={whitelistMutation.isPending}
                  onClick={() => whitelistMutation.mutate({ ip: dhanDetectedIp, ip_flag: "PRIMARY" })}
                  style={{
                    padding: "8px 16px",
                    fontSize: 11,
                    fontWeight: 700,
                    background: "rgba(0, 230, 118, 0.16)",
                    border: "1px solid var(--green)",
                    color: "var(--green)",
                    borderRadius: 4,
                    cursor: "pointer",
                  }}
                >
                  {whitelistMutation.isPending ? "WHITELISTING..." : `WHITELIST DHAN DETECTED IP (${dhanDetectedIp.length > 20 ? dhanDetectedIp.slice(0, 18) + '...' : dhanDetectedIp}) AS PRIMARY`}
                </button>
                <button
                  type="button"
                  disabled={whitelistMutation.isPending}
                  onClick={() => whitelistMutation.mutate({ ip: dhanDetectedIp, ip_flag: "SECONDARY" })}
                  style={{
                    padding: "8px 16px",
                    fontSize: 11,
                    fontWeight: 700,
                    background: "rgba(56, 189, 248, 0.14)",
                    border: "1px solid #38bdf8",
                    color: "#38bdf8",
                    borderRadius: 4,
                    cursor: "pointer",
                  }}
                >
                  WHITELIST DETECTED AS SECONDARY
                </button>
              </>
            ) : null}

            <button
              type="button"
              disabled={whitelistMutation.isPending || serverIp === "unknown"}
              onClick={() => whitelistMutation.mutate({ ip: serverIp, ip_flag: "PRIMARY" })}
              style={{
                padding: "8px 16px",
                fontSize: 11,
                fontWeight: 700,
                background: "rgba(0, 230, 118, 0.12)",
                border: "1px solid var(--green)",
                color: "var(--green)",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              {whitelistMutation.isPending ? "WHITELISTING..." : `WHITELIST SERVER IP (${serverIp}) AS PRIMARY`}
            </button>

            <button
              type="button"
              disabled={whitelistMutation.isPending || serverIp === "unknown"}
              onClick={() => whitelistMutation.mutate({ ip: serverIp, ip_flag: "SECONDARY" })}
              style={{
                padding: "8px 16px",
                fontSize: 11,
                fontWeight: 700,
                background: "rgba(56, 189, 248, 0.12)",
                border: "1px solid #38bdf8",
                color: "#38bdf8",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              WHITELIST SERVER IP AS SECONDARY
            </button>
          </div>

          <div style={{ width: "100%", height: 1, background: "var(--border)", margin: "6px 0" }} />

          {/* Custom IP input */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
              Or Whitelist a Custom Static IP Address:
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", maxWidth: 520 }}>
              <input
                type="text"
                placeholder="e.g. 122.179.45.10"
                value={customIp}
                onChange={(e) => setCustomIp(e.target.value.trim())}
                style={{
                  flex: 1,
                  padding: "7px 10px",
                  fontSize: 12,
                  background: "var(--surface2)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  borderRadius: 4,
                  fontFamily: "var(--font)",
                }}
              />
              <select
                value={ipFlag}
                onChange={(e) => setIpFlag(e.target.value as "PRIMARY" | "SECONDARY")}
                style={{
                  padding: "7px 10px",
                  fontSize: 11,
                  background: "var(--surface2)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  borderRadius: 4,
                  fontWeight: 600,
                }}
              >
                <option value="PRIMARY">PRIMARY</option>
                <option value="SECONDARY">SECONDARY</option>
              </select>
              <button
                type="button"
                disabled={!customIp || whitelistMutation.isPending}
                onClick={() => whitelistMutation.mutate({ ip: customIp, ip_flag: ipFlag })}
                className="connect-btn"
                style={{ whiteSpace: "nowrap" }}
              >
                WHITELIST IP
              </button>
            </div>
          </div>
        </div>

        {/* Informational Guidelines */}
        <div style={{ marginTop: 20, padding: "12px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 4 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--yellow)", letterSpacing: 1 }}>
            IMPORTANT SEBI GUIDELINES & DH-905 TROUBLESHOOTING:
          </div>
          <ul style={{ fontSize: 11, color: "var(--muted)", margin: "6px 0 0 16px", lineHeight: 1.6 }}>
            <li>Dhan only whitelists IPv4 addresses. IPv6 calls will be rejected with DH-905.</li>
            <li>If you update your IP on Dhan, you must generate a fresh Access Token afterwards on web.dhan.co to bind it to the new IP.</li>
            <li>Dhan enforces a lock-in period after modifying an IP before it can be modified again.</li>
          </ul>
        </div>
      </div>
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
      <div className="stat-value" style={{color:color==="green"?"var(--green)":color==="red"?"var(--red)":color==="cyan"?"var(--ba-cyan, #08B6DE)":"var(--text)"}}>
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
