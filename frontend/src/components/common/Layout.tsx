import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

const DESK = [
  { path:"/dashboard",    label:"DASHBOARD",    icon:"▦" },
  { path:"/terminal",     label:"TERMINAL",     icon:"⌨" },
  { path:"/trading",      label:"POSITIONS",    icon:"◈" },
  { path:"/options",      label:"OPTIONS",      icon:"◇" },
  { path:"/copy-trading", label:"COPY TRADING", icon:"⇉" },
  { path:"/risk",         label:"RISK MGMT",    icon:"⚠" },
  { path:"/settings",     label:"SETTINGS",     icon:"⚙" },
];

const CONSOLE = [
  { path:"/strategies", label:"STRATEGIES", icon:"⟳" },
  { path:"/formula",    label:"FORMULA",    icon:"ƒ" },
  { path:"/guide",      label:"GUIDE",      icon:"≡" },
  { path:"/admin",      label:"CONSOLE",    icon:"◉" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  function handleLogout() {
    logout();
    toast.success("Logged out");
    navigate("/login");
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-dot" />
          <span>ALGO<b>TRADE</b></span>
        </div>
        <div className="sidebar-user">
          <div className="user-avatar">{user?.username?.[0]?.toUpperCase()??"T"}</div>
          <div>
            <div className="user-name">{user?.username??"trader"}</div>
            <div className="user-role">{user?.role??"trader"}</div>
          </div>
        </div>
        <nav className="sidebar-nav">
          {DESK.map(({ path, label, icon }) => (
            <Link key={path} to={path} className={`nav-item${pathname===path?" active":""}`}>
              <span className="nav-icon">{icon}</span>
              <span>{label}</span>
              {pathname===path && <div className="nav-active-bar" />}
            </Link>
          ))}
          {user?.role==="admin" && (
            <>
              <div className="nav-section">CONSOLE</div>
              {CONSOLE.map(({ path, label, icon }) => (
                <Link key={path} to={path} className={`nav-item${pathname===path?" active":""}`}>
                  <span className="nav-icon">{icon}</span>
                  <span>{label}</span>
                  {pathname===path && <div className="nav-active-bar" />}
                </Link>
              ))}
            </>
          )}
        </nav>
        <button className="logout-btn" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? "LIGHT MODE" : "DARK MODE"}
        </button>
        <button className="logout-btn" type="button" onClick={handleLogout}>LOGOUT</button>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
