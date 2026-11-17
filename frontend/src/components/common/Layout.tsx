import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import toast from "react-hot-toast";
import {
  Terminal,
  TrendingUp,
  Copy,
  LayoutDashboard,
  Settings,
  SlidersHorizontal,
  Sun,
  Moon,
  LogOut,
} from "lucide-react";

const NAV_ITEMS = [
  { path: "/terminal",     label: "TERMINAL",     icon: Terminal },
  { path: "/trading",      label: "POSITIONS",    icon: TrendingUp },
  { path: "/copy-trading", label: "COPY TRADING", icon: Copy },
  { path: "/dashboard",    label: "DASHBOARD",    icon: LayoutDashboard },
  { path: "/settings",     label: "SETTINGS",     icon: Settings },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { user, logout } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  // Broker status query for global telemetry
  const { data: brokerAccounts } = useQuery({
    queryKey: ["broker-accounts"],
    queryFn: () => api.get("/brokers").then((r) => r.data).catch(() => []),
    staleTime: 30_000,
  });
  const activeBroker = (brokerAccounts || []).find((b: any) => b.is_active);
  const isPaperMode = !activeBroker || Boolean(activeBroker.paper_trading);

  // Funds query for margin in top bar
  const { data: fundsData } = useQuery({
    queryKey: ["dhan-funds"],
    queryFn: () => api.get("/market/funds").then((r) => r.data).catch(() => null),
    refetchInterval: 30_000,
  });

  // Copy trading active account count
  const { data: copyData } = useQuery({
    queryKey: ["copy-trading-summary"],
    queryFn: () => api.get("/copy-trading/accounts").then((r) => r.data).catch(() => null),
    refetchInterval: 15_000,
  });

  function handleLogout() {
    logout();
    toast.success("Logged out");
    navigate("/login");
  }

  const activeCopyCount = (copyData?.child_accounts || []).filter((c: any) => c.is_copy_enabled).length;

  return (
    <div className="layout">
      {/* ── Top Navigation Bar ────────────────────────────────────────── */}
      <header className="top-nav">
        {/* Left Zone: Brand + Nav Links */}
        <div className="top-nav-left">
          <Link to="/terminal" className="top-nav-brand">
            <img
              src="/branding/algo-symbol.svg"
              alt="Algo Platform"
              style={{ width: 24, height: 24, borderRadius: 5, flexShrink: 0 }}
            />
            <span>
              ALGO<b style={{ color: "var(--ba-cyan, #08B6DE)" }}>PLATFORM</b>
            </span>
          </Link>

          <div style={{ width: 1, height: 20, background: "var(--border)" }} />

          <nav className="top-nav-links">
            {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
              const isActive = pathname === path;
              return (
                <Link
                  key={path}
                  to={path}
                  className={`top-nav-link${isActive ? " active" : ""}`}
                >
                  <Icon size={14} />
                  <span>{label}</span>
                </Link>
              );
            })}

            {isAdmin && (
              <Link
                to="/admin"
                className={`top-nav-link${pathname === "/admin" ? " active" : ""}`}
              >
                <SlidersHorizontal size={14} />
                <span>ADMIN CONSOLE</span>
              </Link>
            )}
          </nav>
        </div>

        {/* Center Zone: Endorsement */}
        <div className="top-nav-center">
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "3px 10px",
              background: "rgba(0,0,0,0.25)",
              border: "1px solid var(--border)",
              borderRadius: 4,
            }}
            title="An Independent Product by Bhavin Amesara"
          >
            <img
              src="/branding/ba-monogram.svg"
              alt="BA"
              style={{ width: 18, height: 13, opacity: 0.85 }}
            />
            <span style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 0.8 }}>
              BHAVIN AMESARA
            </span>
          </div>
        </div>

        {/* Right Zone: System Telemetry, Vitals & User Controls */}
        <div className="top-nav-right">
          {activeCopyCount > 0 && (
            <Link
              to="/copy-trading"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                padding: "2px 8px",
                fontSize: 10,
                fontWeight: 700,
                background: "rgba(56, 189, 248, 0.12)",
                border: "1px solid #38bdf8",
                color: "#38bdf8",
                borderRadius: 4,
                textDecoration: "none",
              }}
              title="Active follower accounts copying trades"
            >
              <Copy size={11} />
              <span>COPY: {activeCopyCount} ACCTS</span>
            </Link>
          )}

          {fundsData?.availMargin != null && (
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: "var(--text)",
                background: "rgba(255,255,255,0.03)",
                padding: "3px 8px",
                borderRadius: 4,
                border: "1px solid var(--border)",
              }}
              title="Available trading margin from active broker account"
            >
              Margin: ₹{Number(fundsData.availMargin).toLocaleString()}
            </span>
          )}

          <span
            className={`badge ${isPaperMode ? "badge-yellow" : "badge-green"}`}
            style={{ fontSize: 10, fontWeight: 700 }}
          >
            {isPaperMode ? "PAPER SIM" : (activeBroker?.account_name || "DHAN LIVE")}
          </span>

          <button
            type="button"
            className="top-nav-btn"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
          >
            {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "rgba(255,255,255,0.04)",
              border: "1px solid var(--border)",
              padding: "3px 8px",
              borderRadius: 4,
            }}
          >
            <div
              style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: "var(--green-dim)",
                border: "1px solid var(--green)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--green)",
                fontSize: 10,
                fontWeight: 700,
              }}
            >
              {user?.username?.[0]?.toUpperCase() ?? "T"}
            </div>
            <span style={{ fontSize: 11, fontWeight: 600 }}>{user?.username ?? "trader"}</span>
          </div>

          <button
            type="button"
            className="top-nav-logout"
            onClick={handleLogout}
            title="Sign out of algo platform"
          >
            <LogOut size={13} />
            <span>LOGOUT</span>
          </button>
        </div>
      </header>

      {/* Main full-width page content */}
      <main className="main-content">{children}</main>
    </div>
  );
}
