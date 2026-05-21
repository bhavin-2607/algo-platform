import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
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
        toast("Enter your MFA code", { icon: "🔐" });
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
        <div className="auth-header">
          <div className="status-dot" />
          <span className="status-label">SYSTEM ACCESS</span>
          <h1 className="brand">ALGO<span>TRADE</span></h1>
          <p className="brand-sub">PRIVATE EXECUTION PLATFORM v1.0</p>
        </div>
        <form onSubmit={handleSubmit}>
          <Field label="EMAIL_ADDR" value={email} onChange={setEmail} type="email" placeholder="trader@domain.com" />
          <Field label="PASSWORD" value={password} onChange={setPassword} type="password" placeholder="••••••••••••" />
          {needsMfa && <Field label="MFA_TOKEN" value={mfa} onChange={setMfa} type="text" placeholder="000000" />}
          <button className={`auth-btn${loading ? " loading" : ""}`} type="submit" disabled={loading}>
            {loading ? "AUTHENTICATING..." : "AUTHENTICATE →"}
          </button>
        </form>
        <div className="auth-footer">
          <span>No account? </span>
          <Link to="/register">REQUEST_ACCESS</Link>
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
