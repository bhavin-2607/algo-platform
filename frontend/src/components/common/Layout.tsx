import { useEffect, useState, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import toast from "react-hot-toast";
import {
  Settings,
  SlidersHorizontal,
  Sun,
  Moon,
  LogOut,
  ChevronDown,
} from "lucide-react";

const NAV_ITEMS = [
  { path: "/dashboard",    label: "Dashboard" },
  { path: "/terminal",     label: "Terminal" },
  { path: "/positions",    label: "Positions" },
  { path: "/copy-trading", label: "Copy Trading" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { user, logout } = useAuthStore();
  const isAdmin = user?.role === "admin";
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [menuOpen]);

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
        {/* LEFT SIDE: [LOGO] Algo Platform | Dashboard | Terminal | Positions | Copy Trading */}
        <div className="top-nav-left">
          <Link
            to="/terminal"
            className="top-nav-brand"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              textDecoration: "none",
              color: "var(--text)",
            }}
          >
            <img
              src="/branding/algo-symbol.svg"
              alt="Algo Platform"
              style={{ width: 22, height: 22, borderRadius: 5, flexShrink: 0 }}
            />
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: 0.3 }}>
              Algo Platform
            </span>
          </Link>

          <span style={{ color: "var(--border)", fontSize: 13, userSelect: "none" }}>|</span>

          <nav className="top-nav-links">
            {NAV_ITEMS.map(({ path, label }) => {
              const isActive = pathname === path || (path === "/positions" && pathname === "/trading");
              return (
                <Link
                  key={path}
                  to={path}
                  className={`top-nav-link${isActive ? " active" : ""}`}
                >
                  <span>{label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* RIGHT SIDE: LIVE STATUS | [Gear ICON] Logged in username with dropdown menu */}
        <div className="top-nav-right">
          {/* LIVE STATUS */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "4px 10px",
              background: "rgba(0,0,0,0.22)",
              border: "1px solid var(--border)",
              borderRadius: 4,
            }}
            title={isPaperMode ? "Simulation Paper Trading Mode" : "Connected to DhanHQ Live Trading"}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: isPaperMode ? "var(--yellow)" : "var(--green)",
                boxShadow: isPaperMode
                  ? "0 0 6px rgba(251, 191, 36, 0.6)"
                  : "0 0 6px rgba(0, 230, 118, 0.7)",
              }}
            />
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 0.8,
                color: isPaperMode ? "var(--yellow)" : "var(--green)",
              }}
            >
              {isPaperMode ? "PAPER SIM" : (activeBroker?.account_name || "DHAN LIVE")}
            </span>

            {fundsData?.availMargin != null && (
              <>
                <span style={{ color: "var(--border)", fontSize: 11 }}>•</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)" }}>
                  ₹{Number(fundsData.availMargin).toLocaleString()}
                </span>
              </>
            )}

            {activeCopyCount > 0 && (
              <>
                <span style={{ color: "var(--border)", fontSize: 11 }}>•</span>
                <span style={{ fontSize: 10, fontWeight: 700, color: "#38bdf8" }}>
                  COPY: {activeCopyCount}
                </span>
              </>
            )}
          </div>

          <span style={{ color: "var(--border)", fontSize: 13, userSelect: "none" }}>|</span>

          {/* User Menu: [Gear ICON] Logged in username with dropdown menu */}
          <div ref={menuRef} style={{ position: "relative" }}>
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="top-nav-user-btn"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                padding: "4px 10px",
                background: menuOpen ? "rgba(255, 255, 255, 0.08)" : "rgba(255, 255, 255, 0.03)",
                border: `1px solid ${menuOpen ? "var(--green)" : "var(--border)"}`,
                borderRadius: 4,
                cursor: "pointer",
                color: "var(--text)",
                fontFamily: "var(--font)",
                transition: "all 0.15s ease",
              }}
              title="User Account Menu"
            >
              <Settings size={14} style={{ color: menuOpen ? "var(--green)" : "var(--muted)" }} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>{user?.username ?? "Trader"}</span>
              <ChevronDown
                size={12}
                style={{
                  color: "var(--muted)",
                  transform: menuOpen ? "rotate(180deg)" : "rotate(0deg)",
                  transition: "transform 0.15s",
                }}
              />
            </button>

            {menuOpen && (
              <div className="user-dropdown-menu">
                {/* 1. User Profile */}
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    navigate("/settings");
                  }}
                  className="user-dropdown-item"
                >
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      background: "var(--green-dim)",
                      border: "1px solid var(--green)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--green)",
                      fontSize: 12,
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {user?.username?.[0]?.toUpperCase() ?? "U"}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>User Profile</div>
                    <div style={{ fontSize: 10, color: "var(--muted)" }}>
                      Profile details, Broker & Token settings
                    </div>
                  </div>
                </button>

                {/* 2. Admin Console (only shown when admin is logged in) */}
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      navigate("/admin");
                    }}
                    className="user-dropdown-item"
                  >
                    <SlidersHorizontal size={15} style={{ color: "var(--yellow)", flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>Admin Console</div>
                      <div style={{ fontSize: 10, color: "var(--muted)" }}>
                        IP Whitelisting, Users & System Overview
                      </div>
                    </div>
                  </button>
                )}

                {/* 3. Light Dark option */}
                <button
                  type="button"
                  onClick={() => {
                    setTheme(theme === "dark" ? "light" : "dark");
                  }}
                  className="user-dropdown-item"
                  style={{ justifyContent: "space-between" }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    {theme === "dark" ? (
                      <Sun size={15} style={{ color: "var(--yellow)", flexShrink: 0 }} />
                    ) : (
                      <Moon size={15} style={{ color: "var(--ba-cyan, #08B6DE)", flexShrink: 0 }} />
                    )}
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>Theme Mode</div>
                      <div style={{ fontSize: 10, color: "var(--muted)" }}>
                        Switch to {theme === "dark" ? "Light" : "Dark"} Mode
                      </div>
                    </div>
                  </div>
                  <span className="badge badge-gray" style={{ fontSize: 9 }}>
                    {theme.toUpperCase()}
                  </span>
                </button>

                {/* 4. Personal Branding */}
                <div
                  style={{
                    padding: "10px 14px",
                    background: "rgba(0, 0, 0, 0.2)",
                    borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                  }}
                >
                  <img
                    src="/branding/ba-monogram.svg"
                    alt="BA"
                    style={{ width: 22, height: 16, opacity: 0.9, flexShrink: 0 }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: "var(--text)" }}>
                      BHAVIN AMESARA
                    </div>
                    <div style={{ fontSize: 9, color: "var(--muted)", letterSpacing: 0.3 }}>
                      Independent Quantitative Architecture
                    </div>
                  </div>
                </div>

                {/* 5. Logout Button */}
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    handleLogout();
                  }}
                  className="user-dropdown-item dropdown-logout-btn"
                >
                  <LogOut size={15} style={{ color: "var(--red)", flexShrink: 0 }} />
                  <span style={{ fontSize: 12, fontWeight: 700 }}>Logout</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main full-width page content */}
      <main className="main-content">{children}</main>
    </div>
  );
}
