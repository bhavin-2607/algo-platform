import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi, userApi } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

export default function LoginPage() {
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfa, setMfa] = useState("");
  const [needsMfa, setNeedsMfa] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await authApi.login(email, password, needsMfa ? mfa : undefined);
      setTokens(res.data.access_token, res.data.refresh_token);
      // Fetch full user profile so id, email, role are all populated
      const me = await userApi.me();
      setUser(me.data);
      toast.success("Logged in");
      navigate("/dashboard");
    } catch (err: any) {
      if (err.response?.headers?.["x-mfa-required"]) {
        setNeedsMfa(true);
        toast("Enter your MFA code");
      } else {
        toast.error(err.response?.data?.detail || "Login failed");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-bg">
      <div className="grid-overlay" />
      <div className="glow-blob" />
      <div className="auth-card">
        <Corner pos="tl" /><Corner pos="tr" /><Corner pos="bl" /><Corner pos="br" />
        <div className="auth-header" style={{ textAlign: "center" }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
            <img
              src="/branding/algo-symbol.svg"
              alt="Algo Platform"
              style={{
                width: 52,
                height: 52,
                borderRadius: 12,
                boxShadow: "0 8px 24px rgba(8, 182, 222, 0.25)",
              }}
            />
          </div>
          <span className="status-label" style={{ color: "var(--ba-cyan, #08B6DE)", letterSpacing: 2 }}>SYSTEM ACCESS</span>
          <h1 className="brand" style={{ letterSpacing: 1.5 }}>ALGO<span style={{ color: "var(--ba-cyan, #08B6DE)" }}>PLATFORM</span></h1>
          <p className="brand-sub" style={{ letterSpacing: 1.5 }}>QUANTITATIVE STRATEGY EXECUTION</p>
        </div>
        <form onSubmit={handleSubmit}>
          <Field label="EMAIL_ADDR" value={email} onChange={setEmail} type="email" placeholder="trader@domain.com" />
          <Field label="PASSWORD" value={password} onChange={setPassword} type="password" placeholder="••••••••••••" />
          {needsMfa && <Field label="MFA_TOKEN" value={mfa} onChange={setMfa} type="text" placeholder="000000" />}
          <button className={`auth-btn${loading ? " loading" : ""}`} type="submit" disabled={loading}>
            {loading ? "AUTHENTICATING..." : "AUTHENTICATE"}
          </button>
        </form>
        <div className="auth-footer" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginTop: 18 }}>
          <img
            src="/branding/endorsed-by-ba-dark.svg"
            alt="An Independent Product by Bhavin Amesara"
            style={{ width: 175, height: "auto", opacity: 0.9 }}
          />
          <span style={{ fontSize: 10, color: "var(--muted)" }}>Private Execution Platform · Authorized Access Only</span>
        </div>
      </div>
    </div>
  );
}

function Corner({ pos }: { pos: string }) {
  const s: any = { position: "absolute", width: 12, height: 12, borderColor: "#00ff88", borderStyle: "solid" };
  if (pos === "tl") { s.top = -1; s.left = -1; s.borderWidth = "2px 0 0 2px"; }
  if (pos === "tr") { s.top = -1; s.right = -1; s.borderWidth = "2px 2px 0 0"; }
  if (pos === "bl") { s.bottom = -1; s.left = -1; s.borderWidth = "0 0 2px 2px"; }
  if (pos === "br") { s.bottom = -1; s.right = -1; s.borderWidth = "0 2px 2px 0"; }
  return <div style={s} />;
}

function Field({ label, value, onChange, type, placeholder }: any) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input className="field-input" type={type} value={value}
        onChange={(e) => onChange(e.target.value)} placeholder={placeholder} required />
    </div>
  );
}
