import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authApi, userApi } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();
  const [form, setForm] = useState({ email: "", username: "", password: "" });
  const [loading, setLoading] = useState(false);

  const set = (k: string) => (e: any) => setForm(f => ({ ...f, [k]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await authApi.register(form.email, form.username, form.password);
      setTokens(res.data.access_token, res.data.refresh_token);
      const me = await userApi.me();
      setUser(me.data);
      toast.success("Account created");
      navigate("/dashboard");
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Registration failed");
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
          <span className="status-label">NEW OPERATOR</span>
          <h1 className="brand">ALGO<span>TRADE</span></h1>
          <p className="brand-sub">CREATE SECURE ACCOUNT</p>
        </div>
        <form onSubmit={handleSubmit}>
          <Field label="EMAIL_ADDR" value={form.email}    onChange={set("email")}    type="email"    placeholder="trader@domain.com" />
          <Field label="USERNAME"   value={form.username} onChange={set("username")} type="text"     placeholder="trader_01" />
          <Field label="PASSWORD"   value={form.password} onChange={set("password")} type="password" placeholder="••••••••••••" />
          <button className={`auth-btn${loading ? " loading" : ""}`} type="submit" disabled={loading}>
            {loading ? "CREATING ACCOUNT..." : "CREATE ACCOUNT →"}
          </button>
        </form>
        <div className="auth-footer">
          <span>Have an account? </span>
          <Link to="/login">LOGIN</Link>
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
        onChange={onChange} placeholder={placeholder} required />
    </div>
  );
}
