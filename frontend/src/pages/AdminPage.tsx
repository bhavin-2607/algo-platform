import { Fragment, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import toast from "react-hot-toast";
import { Copy, Check, ChevronDown, ChevronUp, Code, Globe } from "lucide-react";

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
  const [showRawDhan, setShowRawDhan] = useState(false);
  const [copiedRaw, setCopiedRaw] = useState(false);

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
  const ipMatchStatus = data?.ip_match_status;
  const serverIpv4 = data?.current_server_ipv4 || data?.current_server_ip || "Detecting...";
  const serverIpv6 = data?.current_server_ipv6;
  const dhanDetectedIp = data?.dhan_detected_ip;
  const dhanDetectedVersion = data?.dhan_detected_version;
  const primaryIp = data?.dhan_primary_ip || "Not Set";
  const primaryVersion = data?.dhan_primary_version;
  const secondaryIp = data?.dhan_secondary_ip || "Not Set";
  const secondaryVersion = data?.dhan_secondary_version;
  const accountName = data?.account_name || data?.client_id || "Dhan";
  const eligibleDate = data?.modify_eligible_date;
  const modifyDatePrimary = data?.modify_date_primary;
  const modifyDateSecondary = data?.modify_date_secondary;
  const rawDhan = data?.dhan_raw_response;

  function handleCopyJson() {
    if (!rawDhan) return;
    navigator.clipboard.writeText(JSON.stringify(rawDhan, null, 2));
    setCopiedRaw(true);
    toast.success("Dhan API response copied to clipboard");
    setTimeout(() => setCopiedRaw(false), 2000);
  }

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

        {data?.status && data.status !== "SUCCESS" && data?.message && (
          <div
            style={{
              marginTop: 14,
              padding: "10px 14px",
              background: "rgba(255, 23, 68, 0.08)",
              border: "1px solid rgba(255, 23, 68, 0.3)",
              borderRadius: 4,
              fontSize: 12,
              color: "var(--red)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <div>
              <strong>Dhan API Status:</strong> {data.message}
            </div>
            {data.status === "DHAN_ERROR" && (
              <span style={{ fontSize: 11, color: "var(--muted)" }}>
                If token is expired (DH-906), please refresh your access token in User Profile &gt; Settings.
              </span>
            )}
          </div>
        )}

        {/* IP Comparison Grid: 4 Cards (IPv4 & IPv6 Platform Server + Dhan Registered IPs) */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 14, marginTop: 20 }}>
          {/* Card 1: Server IPv4 */}
          <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", padding: "14px 16px", borderRadius: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1.2 }}>CURRENT SERVER IPv4</div>
              <span className="badge badge-gray" style={{ fontSize: 9 }}>IPv4</span>
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: (serverIpv4 === primaryIp || serverIpv4 === secondaryIp) ? "var(--green)" : "var(--yellow)", marginTop: 8, wordBreak: "break-all" }}>
              {serverIpv4}
            </div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
              Platform outbound IPv4 address
            </div>
          </div>

          {/* Card 2: Server IPv6 */}
          <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", padding: "14px 16px", borderRadius: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1.2 }}>CURRENT SERVER IPv6</div>
              <span className="badge badge-gray" style={{ fontSize: 9 }}>IPv6</span>
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, color: (serverIpv6 && (serverIpv6 === primaryIp || serverIpv6 === secondaryIp)) ? "var(--green)" : (serverIpv6 ? "var(--text)" : "var(--muted)"), marginTop: 8, wordBreak: "break-all" }}>
              {serverIpv6 || "Not Detected"}
            </div>
            <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
              Platform outbound IPv6 address
            </div>
          </div>

          {/* Card 3: Dhan Registered Primary IP */}
          <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", padding: "14px 16px", borderRadius: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1.2 }}>DHAN REGISTERED PRIMARY IP</div>
              {primaryVersion && <span className="badge badge-gray" style={{ fontSize: 9 }}>{primaryVersion}</span>}
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: (primaryIp === serverIpv4 || primaryIp === serverIpv6 || primaryIp === dhanDetectedIp) ? "var(--green)" : "var(--text)", marginTop: 8, wordBreak: "break-all" }}>
              {primaryIp}
            </div>
            {modifyDatePrimary ? (
              <div style={{ fontSize: 10, color: "var(--yellow)", marginTop: 4 }}>
                Lock until: <strong>{modifyDatePrimary}</strong>
              </div>
            ) : (
              <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
                Account: {accountName}
              </div>
            )}
          </div>

          {/* Card 4: Dhan Registered Secondary IP */}
          <div style={{ background: "var(--surface2)", border: "1px solid var(--border)", padding: "14px 16px", borderRadius: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1.2 }}>DHAN REGISTERED SECONDARY IP</div>
              {secondaryVersion && <span className="badge badge-gray" style={{ fontSize: 9 }}>{secondaryVersion}</span>}
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, color: (secondaryIp === serverIpv4 || secondaryIp === serverIpv6 || secondaryIp === dhanDetectedIp) ? "var(--green)" : "var(--text)", marginTop: 8, wordBreak: "break-all" }}>
              {secondaryIp}
            </div>
            {modifyDateSecondary ? (
              <div style={{ fontSize: 10, color: "var(--yellow)", marginTop: 4 }}>
                Lock until: <strong>{modifyDateSecondary}</strong>
              </div>
            ) : (
              <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>
                Backup whitelisted IP
              </div>
            )}
          </div>
        </div>

        {eligibleDate && (
          <div style={{ marginTop: 14, fontSize: 11, color: "var(--yellow)" }}>
            Next eligible IP modification date: <strong>{eligibleDate}</strong>
          </div>
        )}
      </div>

      {/* Direct Dhan API Telemetry & Response Card */}
      <div className="card" style={{ padding: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", letterSpacing: 1 }}>
              CURRENT SET IP DATA FROM DHAN (DIRECT API TELEMETRY)
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
              Direct live response from Dhan v2 IP API (<code>GET https://api.dhan.co/v2/ip/getIP</code>).
            </div>
          </div>
          <button
            type="button"
            className="exit-btn"
            onClick={() => setShowRawDhan((v) => !v)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 10,
              padding: "5px 12px",
              color: "var(--green)",
              borderColor: "rgba(0, 230, 118, 0.4)",
            }}
          >
            <Code size={12} />
            <span>{showRawDhan ? "HIDE RAW JSON" : "VIEW DHAN RAW JSON"}</span>
          </button>
        </div>

        {/* Dhan Key Telemetry Row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: 12,
            marginTop: 16,
            padding: "12px 14px",
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            borderRadius: 4,
          }}
        >
          <div>
            <div style={{ fontSize: 9, color: "var(--muted)", letterSpacing: 1 }}>DHAN DETECTED OUTGOING IP</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8", marginTop: 4, wordBreak: "break-all" }}>
              {dhanDetectedIp || "Not Detected"}
            </div>
            {dhanDetectedVersion && (
              <div style={{ fontSize: 9, color: "var(--muted)", marginTop: 2 }}>{dhanDetectedVersion} detected by Dhan server</div>
            )}
          </div>

          <div>
            <div style={{ fontSize: 9, color: "var(--muted)", letterSpacing: 1 }}>DHAN IP MATCH STATUS</div>
            <div style={{ marginTop: 4 }}>
              <span className={`badge ${ipMatchStatus === "MATCH" ? "badge-green" : "badge-red"}`} style={{ fontSize: 10, fontWeight: 700 }}>
                {ipMatchStatus || (isMatched ? "MATCH" : "MISMATCH")}
              </span>
            </div>
          </div>

          <div>
            <div style={{ fontSize: 9, color: "var(--muted)", letterSpacing: 1 }}>TRADING ORDERS PERMITTED</div>
            <div style={{ marginTop: 4 }}>
              <span className={`badge ${ordersAllowed ? "badge-green" : "badge-red"}`} style={{ fontSize: 10, fontWeight: 700 }}>
                {ordersAllowed ? "PERMITTED (ACTIVE)" : "BLOCKED (MISMATCH)"}
              </span>
            </div>
          </div>

          <div>
            <div style={{ fontSize: 9, color: "var(--muted)", letterSpacing: 1 }}>PRIMARY LOCK EXPIRES</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: modifyDatePrimary ? "var(--yellow)" : "var(--green)", marginTop: 4 }}>
              {modifyDatePrimary || "Eligible to modify"}
            </div>
          </div>

          <div>
            <div style={{ fontSize: 9, color: "var(--muted)", letterSpacing: 1 }}>SECONDARY LOCK EXPIRES</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: modifyDateSecondary ? "var(--yellow)" : "var(--green)", marginTop: 4 }}>
              {modifyDateSecondary || "Eligible to modify"}
            </div>
          </div>
        </div>

        {/* Collapsible Raw Dhan JSON Viewer */}
        {showRawDhan && rawDhan && (
          <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--muted)", letterSpacing: 1 }}>
                RAW DHAN API RESPONSE BODY:
              </span>
              <button
                type="button"
                className="exit-btn"
                onClick={handleCopyJson}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  fontSize: 10,
                  padding: "3px 8px",
                }}
              >
                {copiedRaw ? <Check size={11} color="var(--green)" /> : <Copy size={11} />}
                <span>{copiedRaw ? "COPIED" : "COPY JSON"}</span>
              </button>
            </div>
            <pre
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                padding: "12px 14px",
                borderRadius: 4,
                fontSize: 12,
                color: "var(--text)",
                fontFamily: "monospace",
                overflowX: "auto",
                maxHeight: 280,
                margin: 0,
              }}
            >
              {JSON.stringify(rawDhan, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* 1-Click Action & Custom Whitelist Card */}
      <div className="card" style={{ padding: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--green)", letterSpacing: 1, marginBottom: 8 }}>
          WHITELIST IP DIRECTLY ON DHAN (IPv4 & IPv6 SUPPORTED)
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 18 }}>
          Updates the registered static IP on Dhan via the API using your active access token. Supports both IPv4 and IPv6 addresses. Note that exchange regulations enforce a 7-day lock-in period after each modification.
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Quick 1-click whitelist buttons */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {/* Whitelist Server IPv4 */}
            <button
              type="button"
              disabled={whitelistMutation.isPending || serverIpv4 === "unknown"}
              onClick={() => whitelistMutation.mutate({ ip: serverIpv4, ip_flag: "PRIMARY" })}
              style={{
                padding: "8px 14px",
                fontSize: 11,
                fontWeight: 700,
                background: "rgba(0, 230, 118, 0.12)",
                border: "1px solid var(--green)",
                color: "var(--green)",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              {whitelistMutation.isPending ? "WHITELISTING..." : `WHITELIST SERVER IPv4 (${serverIpv4}) AS PRIMARY`}
            </button>

            <button
              type="button"
              disabled={whitelistMutation.isPending || serverIpv4 === "unknown"}
              onClick={() => whitelistMutation.mutate({ ip: serverIpv4, ip_flag: "SECONDARY" })}
              style={{
                padding: "8px 14px",
                fontSize: 11,
                fontWeight: 700,
                background: "rgba(56, 189, 248, 0.12)",
                border: "1px solid #38bdf8",
                color: "#38bdf8",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              WHITELIST SERVER IPv4 AS SECONDARY
            </button>

            {/* Whitelist Server IPv6 (if available) */}
            {serverIpv6 && (
              <>
                <button
                  type="button"
                  disabled={whitelistMutation.isPending}
                  onClick={() => whitelistMutation.mutate({ ip: serverIpv6, ip_flag: "PRIMARY" })}
                  style={{
                    padding: "8px 14px",
                    fontSize: 11,
                    fontWeight: 700,
                    background: "rgba(0, 230, 118, 0.12)",
                    border: "1px solid var(--green)",
                    color: "var(--green)",
                    borderRadius: 4,
                    cursor: "pointer",
                  }}
                  title={serverIpv6}
                >
                  {`WHITELIST SERVER IPv6 (${serverIpv6.length > 18 ? serverIpv6.slice(0, 16) + '...' : serverIpv6}) AS PRIMARY`}
                </button>

                <button
                  type="button"
                  disabled={whitelistMutation.isPending}
                  onClick={() => whitelistMutation.mutate({ ip: serverIpv6, ip_flag: "SECONDARY" })}
                  style={{
                    padding: "8px 14px",
                    fontSize: 11,
                    fontWeight: 700,
                    background: "rgba(56, 189, 248, 0.12)",
                    border: "1px solid #38bdf8",
                    color: "#38bdf8",
                    borderRadius: 4,
                    cursor: "pointer",
                  }}
                  title={serverIpv6}
                >
                  WHITELIST SERVER IPv6 AS SECONDARY
                </button>
              </>
            )}

            {/* Whitelist Dhan Detected IP (if available and distinct) */}
            {dhanDetectedIp && dhanDetectedIp !== serverIpv4 && dhanDetectedIp !== serverIpv6 && (
              <button
                type="button"
                disabled={whitelistMutation.isPending}
                onClick={() => whitelistMutation.mutate({ ip: dhanDetectedIp, ip_flag: "PRIMARY" })}
                style={{
                  padding: "8px 14px",
                  fontSize: 11,
                  fontWeight: 700,
                  background: "rgba(168, 85, 247, 0.12)",
                  border: "1px solid #a855f7",
                  color: "#c084fc",
                  borderRadius: 4,
                  cursor: "pointer",
                }}
                title={dhanDetectedIp}
              >
                {`WHITELIST DHAN DETECTED IP (${dhanDetectedIp.length > 18 ? dhanDetectedIp.slice(0, 16) + '...' : dhanDetectedIp}) AS PRIMARY`}
              </button>
            )}
          </div>

          <div style={{ width: "100%", height: 1, background: "var(--border)", margin: "6px 0" }} />

          {/* Custom IP input (IPv4 or IPv6) */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
              Or Whitelist a Custom Static IP Address (IPv4 or IPv6):
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", maxWidth: 580 }}>
              <input
                type="text"
                placeholder="e.g. 49.36.118.79 or 2405:201:2001:21fa::1"
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
