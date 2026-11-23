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
  Clock,
  Bell,
  Volume2,
  VolumeX,
  Trash2,
  CheckCheck,
  X,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Info,
} from "lucide-react";
import { useNotificationStore, notifyMarket, notifyError } from "@/store/notifications";
import { AstroTelemetryBadge } from "@/components/astro/AstroTelemetryBadge";

function TopNavClock() {
  const [time, setTime] = useState(() => {
    return new Date().toLocaleTimeString("en-IN", {
      timeZone: "Asia/Kolkata",
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  });

  useEffect(() => {
    const id = window.setInterval(() => {
      setTime(
        new Date().toLocaleTimeString("en-IN", {
          timeZone: "Asia/Kolkata",
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      );
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px",
        background: "var(--surface2)",
        border: "1px solid var(--border)",
        borderRadius: 4,
        fontFamily: "monospace",
        fontSize: 11,
        fontWeight: 700,
        color: "var(--text)",
        letterSpacing: 0.5,
      }}
      title="Indian Standard Time (IST)"
    >
      <Clock size={12} style={{ color: "var(--muted)" }} />
      <span>{time}</span>
      <span style={{ fontSize: 9, color: "var(--muted)", fontWeight: 600 }}>IST</span>
    </div>
  );
}

function getMarketSessionInfo() {
  const now = new Date();
  const istDate = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = istDate.getDay();
  const mins = istDate.getHours() * 60 + istDate.getMinutes();

  if (day === 0 || day === 6) {
    return { text: "MARKET CLOSED (WEEKEND)", isOpen: false, isPre: false };
  }
  if (mins >= 540 && mins < 555) {
    return { text: "PRE-MARKET", isOpen: true, isPre: true };
  }
  if (mins >= 555 && mins <= 930) {
    return { text: "MARKET OPEN", isOpen: true, isPre: false };
  }
  if (mins > 930 && mins <= 960) {
    return { text: "POST-MARKET", isOpen: false, isPre: false };
  }
  return { text: "MARKET CLOSED", isOpen: false, isPre: false };
}

function TopNavMarketStatus() {
  const [session, setSession] = useState(() => getMarketSessionInfo());

  useEffect(() => {
    const id = window.setInterval(() => {
      setSession(getMarketSessionInfo());
    }, 5000);
    return () => clearInterval(id);
  }, []);

  const isOpen = session.isOpen;
  const isPre = session.isPre;
  const color = isOpen ? (isPre ? "var(--yellow)" : "var(--green)") : "var(--red)";
  const bg = isOpen
    ? isPre
      ? "rgba(255,183,3,0.1)"
      : "rgba(0,230,118,0.1)"
    : "rgba(255,59,87,0.1)";
  const border = isOpen
    ? isPre
      ? "rgba(255,183,3,0.35)"
      : "rgba(0,230,118,0.35)"
    : "rgba(255,59,87,0.35)";

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 8px",
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 4,
        fontSize: 10,
        fontWeight: 800,
        color: color,
        letterSpacing: 0.8,
      }}
      title="Indian Exchange Market Hours (09:15 - 15:30 IST)"
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: color,
          boxShadow: isOpen ? `0 0 6px ${color}` : "none",
        }}
      />
      <span>{session.text}</span>
    </div>
  );
}

function NotificationBell() {
  const { notifications, soundEnabled, toggleSound, markAsRead, markAllAsRead, clearAll } =
    useNotificationStore();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<"ALL" | "ORDERS" | "ERRORS" | "MARKET">("ALL");
  const drawerRef = useRef<HTMLDivElement | null>(null);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const filtered = notifications.filter((n) => {
    if (filter === "ORDERS") return n.type === "order";
    if (filter === "ERRORS") return n.type === "error";
    if (filter === "MARKET") return n.type === "market";
    return true;
  });

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  return (
    <div ref={drawerRef} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Notification History & Audio Chimes"
        style={{
          position: "relative",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 32,
          height: 30,
          background: open ? "var(--surface2)" : "transparent",
          border: `1px solid ${open ? "var(--green)" : "var(--border)"}`,
          borderRadius: 4,
          cursor: "pointer",
          color: unreadCount > 0 ? "var(--green)" : "var(--muted)",
          transition: "all 0.15s ease",
        }}
      >
        <Bell size={15} />
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: -4,
              right: -4,
              minWidth: 16,
              height: 16,
              padding: "0 4px",
              borderRadius: 8,
              background: "var(--red)",
              color: "#fff",
              fontSize: 9,
              fontWeight: 800,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 6px rgba(255, 59, 87, 0.6)",
              lineHeight: 1,
            }}
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 8px)",
            width: 380,
            maxHeight: 520,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            boxShadow: "0 12px 36px rgba(0, 0, 0, 0.5)",
            zIndex: 9999,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            animation: "fadeUp 0.15s ease",
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "10px 14px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              background: "rgba(255,255,255,0.02)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 1.2, color: "var(--text)" }}>
                NOTIFICATIONS
              </span>
              {unreadCount > 0 && (
                <span
                  style={{
                    background: "rgba(0, 230, 118, 0.15)",
                    color: "var(--green)",
                    border: "1px solid rgba(0, 230, 118, 0.3)",
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "1px 6px",
                    borderRadius: 3,
                  }}
                >
                  {unreadCount} NEW
                </span>
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {/* Sound Toggle */}
              <button
                type="button"
                onClick={toggleSound}
                title={soundEnabled ? "Sound enabled (click to mute)" : "Sound muted (click to unmute)"}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: soundEnabled ? "var(--green)" : "var(--muted)",
                  padding: 2,
                  display: "inline-flex",
                  alignItems: "center",
                }}
              >
                {soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
              </button>

              {/* Mark all read */}
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={markAllAsRead}
                  title="Mark all as read"
                  style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--muted)",
                    padding: 2,
                    display: "inline-flex",
                    alignItems: "center",
                  }}
                >
                  <CheckCheck size={14} />
                </button>
              )}

              {/* Clear all */}
              {notifications.length > 0 && (
                <button
                  type="button"
                  onClick={clearAll}
                  title="Clear all notifications"
                  style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--muted)",
                    padding: 2,
                    display: "inline-flex",
                    alignItems: "center",
                  }}
                >
                  <Trash2 size={14} />
                </button>
              )}

              {/* Close */}
              <button
                type="button"
                onClick={() => setOpen(false)}
                title="Close"
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--muted)",
                  padding: 2,
                  display: "inline-flex",
                  alignItems: "center",
                }}
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Filter Tabs */}
          <div
            style={{
              display: "flex",
              borderBottom: "1px solid var(--border)",
              background: "rgba(0,0,0,0.15)",
              padding: "4px 8px",
              gap: 4,
            }}
          >
            {(["ALL", "ORDERS", "ERRORS", "MARKET"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setFilter(tab)}
                style={{
                  padding: "3px 8px",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: 0.8,
                  borderRadius: 3,
                  border: "none",
                  cursor: "pointer",
                  background: filter === tab ? "var(--surface2)" : "transparent",
                  color: filter === tab ? "var(--green)" : "var(--muted)",
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Notification List */}
          <div style={{ flex: 1, overflowY: "auto", maxHeight: 400 }}>
            {filtered.length === 0 ? (
              <div
                style={{
                  padding: "36px 16px",
                  textAlign: "center",
                  color: "var(--muted)",
                  fontSize: 12,
                }}
              >
                No notifications in this category.
              </div>
            ) : (
              filtered.map((item) => {
                const timeStr = new Date(item.timestamp).toLocaleTimeString("en-IN", {
                  hour12: false,
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                });
                const isBuy = item.side === "BUY";
                const isSell = item.side === "SELL";
                const isError = item.type === "error";
                const isMarket = item.type === "market";

                return (
                  <div
                    key={item.id}
                    onClick={() => markAsRead(item.id)}
                    style={{
                      padding: "8px 12px",
                      borderBottom: "1px solid var(--border)",
                      background: item.read ? "transparent" : "rgba(0, 230, 118, 0.03)",
                      cursor: "pointer",
                      display: "flex",
                      gap: 10,
                      alignItems: "flex-start",
                      transition: "background 0.12s",
                    }}
                  >
                    <div style={{ marginTop: 2, flexShrink: 0 }}>
                      {isError ? (
                        <AlertTriangle size={14} style={{ color: "var(--red)" }} />
                      ) : isBuy ? (
                        <ArrowUpRight size={14} style={{ color: "var(--green)" }} />
                      ) : isSell ? (
                        <ArrowDownRight size={14} style={{ color: "var(--red)" }} />
                      ) : isMarket ? (
                        <Clock size={14} style={{ color: "var(--cyan, #08b6de)" }} />
                      ) : (
                        <Info size={14} style={{ color: "var(--muted)" }} />
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: item.read ? 600 : 700,
                            color: isError ? "var(--red)" : "var(--text)",
                            letterSpacing: 0.5,
                          }}
                        >
                          {item.title}
                        </span>
                        <span style={{ fontSize: 9, color: "var(--muted)", flexShrink: 0, fontFamily: "monospace" }}>
                          {timeStr}
                        </span>
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--muted)",
                          marginTop: 2,
                          lineHeight: 1.4,
                          wordBreak: "break-word",
                        }}
                      >
                        {item.message}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

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
    staleTime: 0,
    refetchInterval: 8_000,
  });
  const activeBroker = (brokerAccounts || []).find((b: any) => b.is_active);
  const isPaperMode = !activeBroker || Boolean(activeBroker.paper_trading);

  // Funds query for margin in top bar
  const { data: fundsData } = useQuery({
    queryKey: ["dhan-funds"],
    queryFn: () => api.get("/market/funds").then((r) => r.data).catch(() => null),
    refetchInterval: 15_000,
  });

  // Copy trading active account count
  const { data: copyData } = useQuery({
    queryKey: ["copy-trading-summary"],
    queryFn: () => api.get("/copy-trading/accounts").then((r) => r.data).catch(() => null),
    refetchInterval: 15_000,
  });

  // DhanHQ token status query for global telemetry
  const { data: dhanStatus } = useQuery({
    queryKey: ["dhan-auth-token-status"],
    queryFn: () => api.get("/dhan-auth/token-status").then((r) => r.data).catch(() => null),
    staleTime: 0,
    refetchInterval: 8_000,
  });
  const tokenOffline = dhanStatus && !dhanStatus.valid;

  // System alerts poller for background execution and broker rejections
  const lastAlertIdRef = useRef<string | null>(null);
  const { data: systemAlerts } = useQuery({
    queryKey: ["system-alerts"],
    queryFn: () => api.get("/terminal/alerts?limit=10").then((r) => r.data).catch(() => []),
    refetchInterval: 5_000,
  });

  useEffect(() => {
    if (!systemAlerts || !Array.isArray(systemAlerts) || systemAlerts.length === 0) return;
    const latest = systemAlerts[0];
    if (!latest || !latest.id) return;
    if (lastAlertIdRef.current === null) {
      lastAlertIdRef.current = latest.id;
      return;
    }
    if (latest.id !== lastAlertIdRef.current) {
      const newAlerts: any[] = [];
      for (const a of systemAlerts) {
        if (a.id === lastAlertIdRef.current) break;
        newAlerts.push(a);
      }
      lastAlertIdRef.current = latest.id;
      newAlerts.reverse().forEach((a: any) => {
        toast.error(a.message);
        notifyError(a.kind || "SYSTEM ALERT", a.message);
      });
    }
  }, [systemAlerts]);

  // Market hours watchdog for 9:15 AM (Open) and 3:30 PM (Closed) IST chimes
  useEffect(() => {
    let lastChecked = "";
    const timer = setInterval(() => {
      const istDate = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
      const day = istDate.getDay();
      if (day < 1 || day > 5) return; // Monday to Friday only

      const dateStr = istDate.toISOString().slice(0, 10);
      const hours = istDate.getHours();
      const minutes = istDate.getMinutes();
      const seconds = istDate.getSeconds();

      if (hours === 9 && minutes === 15 && seconds < 6) {
        const key = `${dateStr}-open`;
        if (lastChecked !== key) {
          lastChecked = key;
          notifyMarket("OPEN", "NSE/BSE/MCX market session is open (09:15 IST).");
        }
      } else if (hours === 15 && minutes === 30 && seconds < 6) {
        const key = `${dateStr}-close`;
        if (lastChecked !== key) {
          lastChecked = key;
          notifyMarket("CLOSED", "NSE/BSE equity & F&O market session has concluded (15:30 IST).");
        }
      }
    }, 2000);

    return () => clearInterval(timer);
  }, []);

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

        {/* RIGHT SIDE: Clock | LIVE STATUS | [Gear ICON] Logged in username with dropdown menu */}
        <div className="top-nav-right">
          {/* Clock */}
          <TopNavClock />

          {/* Market Status (OPEN / CLOSED) */}
          <TopNavMarketStatus />

          {/* Financial Astrology & Cyclical Timing Badge (Watch Only) */}
          <AstroTelemetryBadge />

          <span style={{ color: "var(--border)", fontSize: 13, userSelect: "none" }}>|</span>

          {/* LIVE STATUS */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "4px 10px",
              background: "var(--surface2)",
              border: `1px solid ${tokenOffline ? "rgba(255, 23, 68, 0.45)" : "var(--border)"}`,
              borderRadius: 4,
            }}
            title={
              tokenOffline
                ? "DhanHQ session offline or token expired. Please refresh token in Settings / Profile."
                : isPaperMode
                ? "Simulation Paper Trading Mode"
                : "Connected to DhanHQ Live Trading"
            }
          >
            {tokenOffline ? (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  fontSize: 10,
                  fontWeight: 800,
                  letterSpacing: 0.8,
                  color: "var(--red)",
                }}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: "var(--red)",
                    boxShadow: "0 0 6px rgba(255, 23, 68, 0.85)",
                  }}
                />
                OFFLINE
              </span>
            ) : (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: 0.8,
                  color: isPaperMode ? "var(--yellow)" : "var(--green)",
                }}
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
                {isPaperMode ? "PAPER SIM" : (activeBroker?.account_name || "DHAN LIVE")}
              </span>
            )}

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
                <span style={{ fontSize: 10, fontWeight: 700, color: "#0284c7" }}>
                  COPY: {activeCopyCount}
                </span>
              </>
            )}
          </div>

          {/* Notification History Bell & Audio Chimes */}
          <NotificationBell />

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
                background: menuOpen ? "var(--surface2)" : "transparent",
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
                    background: "var(--surface2)",
                    borderBottom: "1px solid var(--border)",
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
