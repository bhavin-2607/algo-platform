import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";
import {
  LayoutDashboard,
  Terminal,
  TrendingUp,
  Copy,
  ShieldAlert,
  Settings,
  Sliders,
  Code2,
  BookOpen,
  SlidersHorizontal,
  Sun,
  Moon,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const DESK = [
  { path:"/dashboard",    label:"DASHBOARD",    icon: LayoutDashboard },
  { path:"/terminal",     label:"TERMINAL",     icon: Terminal },
  { path:"/trading",      label:"POSITIONS",    icon: TrendingUp },
  { path:"/copy-trading", label:"COPY TRADING", icon: Copy },
  { path:"/risk",         label:"RISK MGMT",    icon: ShieldAlert },
  { path:"/settings",     label:"SETTINGS",     icon: Settings },
];

const CONSOLE = [
  { path:"/strategies", label:"STRATEGIES", icon: Sliders },
  { path:"/formula",    label:"FORMULA",    icon: Code2 },
  { path:"/guide",      label:"GUIDE",      icon: BookOpen },
  { path:"/admin",      label:"CONSOLE",    icon: SlidersHorizontal },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar-collapsed") === "1");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  function handleLogout() {
    logout();
    toast.success("Logged out");
    navigate("/login");
  }

  return (
    <div className="layout">
      <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-dot" />
          {!collapsed && <span>ALGO<b>TRADE</b></span>}
          <button type="button" className="sidebar-toggle" onClick={() => setCollapsed(v => !v)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>
        <div className="sidebar-user">
          <div className="user-avatar">{user?.username?.[0]?.toUpperCase()??"T"}</div>
          {!collapsed && (
            <div>
              <div className="user-name">{user?.username??"trader"}</div>
              <div className="user-role">{user?.role??"trader"}</div>
            </div>
          )}
        </div>
        <nav className="sidebar-nav">
          {DESK.map(({ path, label, icon: Icon }) => (
            <Link key={path} to={path} title={label} className={`nav-item${pathname===path?" active":""}`}>
              <Icon size={16} className="nav-icon" />
              {!collapsed && <span>{label}</span>}
              {pathname===path && <div className="nav-active-bar" />}
            </Link>
          ))}
          {user?.role==="admin" && (
            <>
              {!collapsed && <div className="nav-section">CONSOLE</div>}
              {CONSOLE.map(({ path, label, icon: Icon }) => (
                <Link key={path} to={path} title={label} className={`nav-item${pathname===path?" active":""}`}>
                  <Icon size={16} className="nav-icon" />
                  {!collapsed && <span>{label}</span>}
                  {pathname===path && <div className="nav-active-bar" />}
                </Link>
              ))}
            </>
          )}
        </nav>
        <button className="logout-btn" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} style={{display:"flex", alignItems:"center", justifyContent:"center", gap:8}}>
          {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
          {!collapsed && <span>{theme === "dark" ? "LIGHT MODE" : "DARK MODE"}</span>}
        </button>
        <button className="logout-btn" type="button" onClick={handleLogout} style={{display:"flex", alignItems:"center", justifyContent:"center", gap:8}}>
          <LogOut size={14} />
          {!collapsed && <span>LOGOUT</span>}
        </button>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
