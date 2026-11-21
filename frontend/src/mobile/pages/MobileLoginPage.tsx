import React, { useState } from "react";
import { Lock, User, Eye, EyeOff, ShieldCheck, Loader2, Sun, Moon } from "lucide-react";
import { authApi, userApi } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

interface MobileLoginPageProps {
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onLoginSuccess: () => void;
}

export const MobileLoginPage: React.FC<MobileLoginPageProps> = ({
  theme,
  onToggleTheme,
  onLoginSuccess,
}) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const { setTokens, setUser } = useAuthStore();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      toast.error("Please enter both username and password");
      return;
    }

    setIsLoading(true);
    try {
      const res = await authApi.login(username.trim(), password);
      setTokens(res.data.access_token, res.data.refresh_token);

      const me = await userApi.me();
      setUser(me.data);

      toast.success(`Welcome ${me.data.username || "Trader"}`);
      onLoginSuccess();
    } catch (err: any) {
      const msg = err.response?.data?.detail || "Invalid credentials. Verify password set on Pi.";
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="mobile-app-shell justify-between px-6 py-8 relative">
      {/* Top Bar with Theme Toggle */}
      <div className="flex items-center justify-between w-full max-w-sm mx-auto">
        <div className="w-8" />
        <div
          className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-[11px] font-mono"
          style={{ background: "var(--surface2)", border: "1px solid var(--border)", color: "var(--muted)" }}
        >
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "var(--green)" }} />
          <span>pyregex.dpdns.org</span>
        </div>
        <button
          onClick={onToggleTheme}
          title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
          className="p-2 rounded-xl transition-all active:scale-95"
          style={{ background: "var(--surface2)", border: "1px solid var(--border)", color: "var(--text)" }}
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </div>

      {/* Branding */}
      <div className="space-y-4 text-center my-auto">
        <div className="flex justify-center">
          <img
            src="/branding/algo-symbol.svg"
            alt="Algo Platform Logo"
            className="w-16 h-16 shadow-xl"
            style={{
              borderRadius: 16,
              boxShadow: "0 8px 24px rgba(8, 182, 222, 0.25)",
            }}
          />
        </div>

        <div>
          <h1 className="text-2xl font-black tracking-tight" style={{ color: "var(--text)" }}>
            ALGO <span style={{ color: "var(--ba-cyan, var(--blue))" }}>MOBILE</span>
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
            Autonomous Trading Execution & Monitoring
          </p>
        </div>

        {/* Login Form */}
        <div
          className="w-full max-w-sm mx-auto p-5 rounded-2xl text-left space-y-4"
          style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "0 8px 30px rgba(0,0,0,0.08)" }}
        >
          <form onSubmit={handleLogin} className="space-y-4">
            {/* Username */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>
                Username
              </label>
              <div className="relative">
                <User size={16} className="absolute left-3.5 top-3.5" style={{ color: "var(--muted)" }} />
                <input
                  type="text"
                  autoCapitalize="none"
                  autoCorrect="off"
                  placeholder="Enter username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full h-11 pl-10 pr-3 rounded-xl text-sm focus:outline-hidden"
                  style={{
                    background: "var(--surface2)",
                    border: "1px solid var(--border)",
                    color: "var(--text)",
                  }}
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold" style={{ color: "var(--text)" }}>
                Password (Set on Pi)
              </label>
              <div className="relative">
                <Lock size={16} className="absolute left-3.5 top-3.5" style={{ color: "var(--muted)" }} />
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-11 pl-10 pr-10 rounded-xl text-sm focus:outline-hidden"
                  style={{
                    background: "var(--surface2)",
                    border: "1px solid var(--border)",
                    color: "var(--text)",
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-3.5"
                  style={{ color: "var(--muted)" }}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full h-12 mt-2 rounded-xl font-bold text-sm flex items-center justify-center space-x-2 transition-all active:scale-98 shadow-md"
              style={{
                background: "var(--green)",
                color: "var(--bg)",
              }}
            >
              {isLoading ? <Loader2 size={18} className="animate-spin" /> : <ShieldCheck size={18} />}
              <span>{isLoading ? "Authenticating with Pi..." : "Sign In to Terminal"}</span>
            </button>
          </form>

          <p className="text-[11px] text-center leading-relaxed" style={{ color: "var(--muted)" }}>
            Credentials authenticate directly against PostgreSQL on the Raspberry Pi.
          </p>
        </div>
      </div>

      {/* Footer */}
      <div className="flex flex-col items-center space-y-2 pb-2">
        <img
          src={theme === "dark" ? "/branding/endorsed-by-ba-dark.svg" : "/branding/endorsed-by-ba-light.svg"}
          alt="An Independent Product by Bhavin Amesara"
          style={{ width: 155, height: "auto", opacity: 0.85 }}
        />
        <div className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
          Algo Platform Mobile • Authorized Access Only
        </div>
      </div>
    </div>
  );
};
