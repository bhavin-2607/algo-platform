import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { useAuthStore } from "@/store/auth";
import { userApi, api } from "@/utils/api";
import toast from "react-hot-toast";

export default function SettingsPage() {
  const [tab, setTab] = useState<"profile" | "security" | "mfa" | "notifications">("profile");

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">SETTINGS</h1>
          <p className="page-sub">Account configuration & security</p>
        </div>
      </div>
      <div className="tab-switcher" style={{ marginBottom: 24 }}>
        <button className={`tab-btn${tab === "profile"  ? " active" : ""}`} onClick={() => setTab("profile")}>PROFILE</button>
        <button className={`tab-btn${tab === "security" ? " active" : ""}`} onClick={() => setTab("security")}>SECURITY</button>
        <button className={`tab-btn${tab === "mfa"      ? " active" : ""}`} onClick={() => setTab("mfa")}>MFA</button>
      </div>
      {tab === "profile"  && <ProfileTab />}
      {tab === "security" && <SecurityTab />}
      {tab === "mfa"      && <MfaTab />}
    </Layout>
  );
}

/* ── PROFILE ─────────────────────────────────────────────── */
function ProfileTab() {
  const { setUser } = useAuthStore();

  const { data: me, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: () => userApi.me().then(r => r.data),
  });

  const [username, setUsername] = useState("");

  // Set username from fetched data once loaded
  if (me && !username && me.username) {
    setUsername(me.username);
  }

  const saveMutation = useMutation({
    mutationFn: () => userApi.updateProfile(username),
    onSuccess: async () => {
      const fresh = await userApi.me();
      setUser(fresh.data);
      toast.success("Profile updated");
    },
    onError: () => toast.error("Failed to update profile"),
  });

  if (isLoading) return <div style={{ color: "var(--muted)", padding: 20, fontSize: 12 }}>Loading...</div>;

  return (
    <div style={{ maxWidth: 540 }}>
      <div className="card">
        <div className="card-header">
          <span className="card-title">ACCOUNT PROFILE</span>
          <span className={`badge ${me?.role === "admin" ? "badge-yellow" : "badge-gray"}`}>
            {(me?.role ?? "trader").toUpperCase()}
          </span>
        </div>
        <div style={{ padding: "24px 24px 8px" }}>
          {/* Avatar */}
          <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 28,
            paddingBottom: 24, borderBottom: "1px solid var(--border)" }}>
            <div style={{
              width: 64, height: 64, borderRadius: "50%",
              background: "var(--green-dim)", border: "2px solid var(--green)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 24, fontWeight: 700, color: "var(--green)",
            }}>
              {(me?.username?.[0] ?? "T").toUpperCase()}
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{me?.username}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{me?.email}</div>
              <div style={{ fontSize: 10, color: "var(--green)", marginTop: 6, letterSpacing: 1 }}>● ACTIVE TRADER</div>
            </div>
          </div>

          <SField label="USERNAME" value={username} onChange={setUsername} type="text" />
          <SField label="EMAIL" value={me?.email ?? ""} onChange={() => {}} type="email" disabled note="Contact admin to change email" />
          <SField label="ACCOUNT ID" value={me?.id ?? "—"} onChange={() => {}} type="text" disabled />
          <SField label="MEMBER SINCE" value={me?.created_at ? new Date(me.created_at).toLocaleDateString() : "—"} onChange={() => {}} type="text" disabled />

          <button
            className={`auth-btn${saveMutation.isPending ? " loading" : ""}`}
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            style={{ marginTop: 8 }}
          >
            {saveMutation.isPending ? "SAVING..." : "SAVE CHANGES →"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── SECURITY ─────────────────────────────────────────────── */
function SecurityTab() {
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const set = (k: string) => (v: string) => setForm(f => ({ ...f, [k]: v }));

  const changeMutation = useMutation({
    mutationFn: () => userApi.changePassword(form.current, form.next),
    onSuccess: () => {
      toast.success("Password changed successfully");
      setForm({ current: "", next: "", confirm: "" });
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed to change password"),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (form.next !== form.confirm) { toast.error("Passwords don't match"); return; }
    if (form.next.length < 8) { toast.error("Password must be 8+ characters"); return; }
    changeMutation.mutate();
  }

  return (
    <div style={{ maxWidth: 540 }}>
      <div className="card">
        <div className="card-header"><span className="card-title">CHANGE PASSWORD</span></div>
        <div style={{ padding: "24px 24px 8px" }}>
          <form onSubmit={handleSubmit}>
            <SField label="CURRENT PASSWORD" value={form.current} onChange={set("current")} type="password" />
            <SField label="NEW PASSWORD"      value={form.next}    onChange={set("next")}    type="password" />
            <SField label="CONFIRM PASSWORD"  value={form.confirm} onChange={set("confirm")} type="password" />
            <button
              className={`auth-btn${changeMutation.isPending ? " loading" : ""}`}
              type="submit" disabled={changeMutation.isPending}
              style={{ marginTop: 8 }}
            >
              {changeMutation.isPending ? "UPDATING..." : "UPDATE PASSWORD →"}
            </button>
          </form>
        </div>
      </div>
      <div className="info-box" style={{ marginTop: 16 }}>
        <div className="info-icon">🔒</div>
        <div>
          <div className="info-title">SECURITY RECOMMENDATIONS</div>
          <div className="info-body">
            Use 12+ characters with mixed case, numbers and symbols.
            Enable MFA for an extra layer of protection.
            Session tokens expire every 30 minutes automatically.
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── MFA ──────────────────────────────────────────────────── */
function MfaTab() {
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: () => userApi.me().then(r => r.data) });
  const [qrUri,  setQrUri]  = useState("");
  const [secret, setSecret] = useState("");
  const [token,  setToken]  = useState("");
  const [step,   setStep]   = useState<"idle" | "setup" | "verify">("idle");

  async function startSetup() {
    try {
      const res = await api.post("/auth/mfa/setup");
      setQrUri(res.data.qr_uri);
      setSecret(res.data.secret);
      setStep("setup");
    } catch { toast.error("Failed to start MFA setup"); }
  }

  async function verifyToken(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.post("/auth/mfa/verify", { token });
      toast.success("MFA enabled successfully!");
      setStep("idle");
    } catch { toast.error("Invalid token — try again"); }
  }

  return (
    <div style={{ maxWidth: 540 }}>
      <div className="card">
        <div className="card-header">
          <span className="card-title">TWO-FACTOR AUTH</span>
          <span className={`badge ${me?.mfa_enabled ? "badge-green" : "badge-gray"}`}>
            {me?.mfa_enabled ? "ENABLED" : "DISABLED"}
          </span>
        </div>
        <div style={{ padding: 24 }}>
          {step === "idle" && (
            <>
              <p style={{ color: "var(--muted)", fontSize: 12, lineHeight: 1.8, marginBottom: 20 }}>
                Adds an extra layer of security. You'll need Google Authenticator or Authy.
              </p>
              <button className="connect-btn" onClick={startSetup}>
                {me?.mfa_enabled ? "RECONFIGURE MFA" : "ENABLE MFA →"}
              </button>
            </>
          )}
          {step === "setup" && (
            <>
              <p style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>Scan with your authenticator app:</p>
              <a
                href={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrUri)}`}
                target="_blank" rel="noreferrer"
              >
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrUri)}`}
                  alt="MFA QR Code"
                  style={{ display: "block", margin: "0 0 16px", border: "4px solid white" }}
                />
              </a>
              <div style={{ padding: "12px 14px", background: "var(--surface2)", border: "1px solid var(--border)", marginBottom: 16 }}>
                <div style={{ color: "var(--green)", fontSize: 10, marginBottom: 6, letterSpacing: 1 }}>MANUAL ENTRY KEY</div>
                <div style={{ fontSize: 12, letterSpacing: 2, color: "var(--text)" }}>{secret}</div>
              </div>
              <button className="connect-btn" onClick={() => setStep("verify")} style={{ width: "100%" }}>
                I'VE SCANNED IT →
              </button>
            </>
          )}
          {step === "verify" && (
            <form onSubmit={verifyToken}>
              <p style={{ color: "var(--muted)", fontSize: 12, marginBottom: 16 }}>
                Enter the 6-digit code from your authenticator:
              </p>
              <SField label="MFA CODE" value={token} onChange={setToken} type="text" placeholder="000000" />
              <button className="auth-btn" type="submit">VERIFY & ENABLE →</button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Shared field ─────────────────────────────────────────── */
function SField({ label, value, onChange, type, disabled, note, placeholder }: any) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input
        className="field-input" type={type} value={value}
        placeholder={placeholder}
        onChange={(e) => !disabled && onChange(e.target.value)}
        disabled={disabled}
        style={disabled ? { opacity: 0.4, cursor: "not-allowed" } : {}}
      />
      {note && <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>{note}</div>}
    </div>
  );
}

// Add this export at the bottom for the NotificationsTab used in SettingsPage
export function NotificationsTab() {
  const [form, setForm] = useState({
    telegram_chat_id:"", notify_signals:true, notify_kills:true,
    notify_fills:true, notify_risk_warnings:true,
  });
  const [testing, setTesting] = useState(false);

  useQuery({
    queryKey:["notification-settings"],
    queryFn:()=>api.get("/notifications/settings").then(r=>{ setForm(r.data); return r.data; }),
  });

  const saveMutation = useMutation({
    mutationFn:()=>api.put("/notifications/settings", form),
    onSuccess:()=>toast.success("Notification settings saved"),
    onError:()=>toast.error("Failed to save"),
  });

  async function testTelegram() {
    setTesting(true);
    try {
      await api.post("/notifications/test");
      toast.success("Test message sent! Check your Telegram.");
    } catch(e:any) {
      toast.error(e.response?.data?.detail||"Test failed");
    } finally { setTesting(false); }
  }

  return (
    <div style={{maxWidth:540}}>
      <div className="card">
        <div className="card-header"><span className="card-title">TELEGRAM NOTIFICATIONS</span></div>
        <div style={{padding:"24px 24px 8px"}}>
          <div className="info-box" style={{marginBottom:20}}>
            <div className="info-icon">📱</div>
            <div>
              <div className="info-title">SETUP TELEGRAM ALERTS</div>
              <div className="info-body">
                1. Message <code>@AlgoTradeNotifyBot</code> on Telegram<br/>
                2. Send <code>/start</code> to get your Chat ID<br/>
                3. Paste it below and save
              </div>
            </div>
          </div>

          <SField label="TELEGRAM CHAT ID" value={form.telegram_chat_id}
            onChange={(v:string)=>setForm(f=>({...f,telegram_chat_id:v}))}
            type="text" placeholder="e.g. 123456789" />

          <div style={{marginBottom:20}}>
            <label className="field-label" style={{marginBottom:12,display:"block"}}>NOTIFY ME FOR</label>
            {[
              {key:"notify_signals",  label:"Copy trade signals received"},
              {key:"notify_kills",    label:"Kill switch triggered"},
              {key:"notify_fills",    label:"Orders filled"},
              {key:"notify_risk_warnings", label:"Risk limit warnings (>80%)"},
            ].map(({key,label})=>(
              <div key={key} style={{
                display:"flex",justifyContent:"space-between",alignItems:"center",
                padding:"10px 0",borderBottom:"1px solid var(--border)",
              }}>
                <span style={{fontSize:12,color:"var(--text)"}}>{label}</span>
                <button type="button"
                  onClick={()=>setForm(f=>({...f,[key]:!f[key as keyof typeof f]}))}
                  style={{
                    width:44,height:24,borderRadius:12,border:"none",
                    cursor:"pointer",transition:"all 0.2s",
                    background:(form as any)[key]?"var(--green)":"var(--surface2)",
                    position:"relative",
                  }}>
                  <div style={{
                    position:"absolute",top:3,
                    left:(form as any)[key]?20:3,
                    width:18,height:18,borderRadius:"50%",
                    background:"white",transition:"left 0.2s",
                  }}/>
                </button>
              </div>
            ))}
          </div>

          <div style={{display:"flex",gap:8,marginBottom:8}}>
            <button className="auth-btn" onClick={()=>saveMutation.mutate()}
              disabled={saveMutation.isPending} style={{flex:1}}>
              {saveMutation.isPending?"SAVING...":"SAVE SETTINGS →"}
            </button>
            <button className="connect-btn" onClick={testTelegram}
              disabled={testing||!form.telegram_chat_id}>
              {testing?"SENDING...":"TEST"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
