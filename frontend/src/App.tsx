import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import { useAuthStore } from "@/store/auth";
import LoginPage       from "@/pages/LoginPage";
import RegisterPage    from "@/pages/RegisterPage";
import DashboardPage   from "@/pages/DashboardPage";
import TradingPage     from "@/pages/TradingPage";
import OptionsPage    from "@/pages/OptionsPage";
import StrategiesPage  from "@/pages/StrategiesPage";
import SettingsPage    from "@/pages/SettingsPage";
import CopyTradingPage from "@/pages/CopyTradingPage";
import RiskPage        from "@/pages/RiskPage";
import TerminalPage    from "@/pages/TerminalPage";
import FormulaPage     from "@/pages/FormulaPage";
import AdminPage       from "@/pages/AdminPage";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

function Protected({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.accessToken);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}
function AdminOnly({ children }: { children: React.ReactNode }) {
  const isAdmin = useAuthStore((s) => s.isAdmin());
  return isAdmin ? <>{children}</> : <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Toaster position="top-right" toastOptions={{
          style: { background:"#0d1117", color:"#e8f5e9",
            border:"1px solid rgba(0,255,136,0.2)",
            fontFamily:"JetBrains Mono, monospace", fontSize:12 },
        }} />
        <Routes>
          <Route path="/login"        element={<LoginPage />} />
          <Route path="/register"     element={<RegisterPage />} />
          <Route path="/dashboard"    element={<Protected><DashboardPage /></Protected>} />
          <Route path="/terminal"     element={<Protected><TerminalPage /></Protected>} />
          <Route path="/trading"      element={<Protected><TradingPage /></Protected>} />
          <Route path="/options" element={<Protected><OptionsPage /></Protected>} />
          <Route path="/strategies"   element={<Protected><StrategiesPage /></Protected>} />
          <Route path="/formula"      element={<Protected><FormulaPage /></Protected>} />
          <Route path="/copy-trading" element={<Protected><CopyTradingPage /></Protected>} />
          <Route path="/risk"         element={<Protected><RiskPage /></Protected>} />
          <Route path="/settings"     element={<Protected><SettingsPage /></Protected>} />
          <Route path="/admin"        element={<Protected><AdminOnly><AdminPage /></AdminOnly></Protected>} />
          <Route path="*"             element={<Navigate to="/terminal" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
