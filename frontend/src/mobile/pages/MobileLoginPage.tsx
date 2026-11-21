import React, { useState } from "react";
import { Lock, User, Eye, EyeOff, ShieldCheck, Loader2 } from "lucide-react";
import { authApi, userApi } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

interface MobileLoginPageProps {
  onLoginSuccess: () => void;
}

export const MobileLoginPage: React.FC<MobileLoginPageProps> = ({ onLoginSuccess }) => {
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
    <div className="min-h-screen bg-zinc-950 flex flex-col justify-between px-6 py-10">
      {/* Top Branding */}
      <div className="space-y-6 pt-4 text-center">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-500 mx-auto flex items-center justify-center shadow-lg shadow-emerald-950/50">
          <span className="font-black text-white text-xl tracking-wider">BA</span>
        </div>

        <div>
          <h1 className="text-2xl font-black text-white tracking-tight">ALGO MOBILE</h1>
          <p className="text-xs text-zinc-400 mt-1">Autonomous Trading Execution & Monitoring</p>
        </div>

        {/* Server Connection Banner */}
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 bg-zinc-900 border border-zinc-800 rounded-full text-[11px] text-zinc-400 font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>pyregex.dpdns.org</span>
        </div>
      </div>

      {/* Login Form */}
      <div className="w-full max-w-sm mx-auto space-y-5">
        <form onSubmit={handleLogin} className="space-y-4">
          {/* Username */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-zinc-300">Username</label>
            <div className="relative">
              <User size={16} className="absolute left-3.5 top-3 text-zinc-500" />
              <input
                type="text"
                autoCapitalize="none"
                autoCorrect="off"
                placeholder="Enter username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full h-11 pl-10 pr-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-hidden"
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-zinc-300">Password (Set on Pi)</label>
            <div className="relative">
              <Lock size={16} className="absolute left-3.5 top-3 text-zinc-500" />
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-11 pl-10 pr-10 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-hidden"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-3 text-zinc-500 hover:text-zinc-300"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full h-12 mt-2 bg-emerald-600 hover:bg-emerald-500 active:scale-98 text-white rounded-xl font-bold text-sm flex items-center justify-center space-x-2 transition-all shadow-lg shadow-emerald-950/40"
          >
            {isLoading ? <Loader2 size={18} className="animate-spin" /> : <ShieldCheck size={18} />}
            <span>{isLoading ? "Authenticating with Pi..." : "Sign In to Terminal"}</span>
          </button>
        </form>

        <p className="text-[11px] text-zinc-400 text-center leading-relaxed">
          Authentication is verified strictly against PostgreSQL on the Raspberry Pi.
        </p>
      </div>

      {/* Footer */}
      <div className="text-center text-[10px] text-zinc-400 font-mono">
        Algo Platform Mobile • v1.0.0
      </div>
    </div>
  );
};
