import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";

const NAV = [
  { path:"/dashboard",    label:"DASHBOARD",    icon:"▦" },
  { path:"/market",      label:"LIVE MARKET",  icon:"◉" },
  { path:"/terminal",     label:"TERMINAL",     icon:"⌨" },
  { path:"/trading",      label:"POSITIONS",    icon:"◈" },
  { path:"/charts",       label:"CHARTS",       icon:"📈" },
  { path:"/strategies",   label:"STRATEGIES",   icon:"⟳" },
  { path:"/formula",      label:"FORMULA",      icon:"ƒ" },
  { path:"/copy-trading", label:"COPY TRADING", icon:"⇉" },
  { path:"/risk",         label:"RISK MGMT",    icon:"⚠" },
  { path:"/settings",     label:"SETTINGS",     icon:"⚙" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

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
          {NAV.map(({ path, label, icon }) => (
            <Link key={path} to={path} className={`nav-item${pathname===path?" active":""}`}>
              <span className="nav-icon">{icon}</span>
              <span>{label}</span>
              {pathname===path && <div className="nav-active-bar" />}
            </Link>
          ))}
          {user?.role==="admin" && (
            <Link to="/admin" className={`nav-item${pathname==="/admin"?" active":""}`}>
              <span className="nav-icon">◉</span>
              <span>ADMIN</span>
              {pathname==="/admin" && <div className="nav-active-bar" />}
            </Link>
          )}
        </nav>
        <button className="logout-btn" onClick={handleLogout}>⏻ LOGOUT</button>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
