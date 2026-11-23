import React, { useState, useEffect, useRef, useCallback } from "react";
import { Capacitor } from "@capacitor/core";
import { StatusBar, Style } from "@capacitor/status-bar";
import { useAuthStore } from "@/store/auth";
import { api } from "@/utils/api";
import { wsBase } from "@/utils/ws";
import { MobileHeader } from "./components/MobileHeader";
import { MobileBottomNav, MobileTab } from "./components/MobileBottomNav";
import { MobileAlgoPage } from "./pages/MobileAlgoPage";
import { MobileWatchlistPage } from "./pages/MobileWatchlistPage";
import { MobileAstroPage } from "./pages/MobileAstroPage";
import { MobileLoginPage } from "./pages/MobileLoginPage";
import { AlgoRowData } from "./components/AlgoSmartCard";
import { WatchlistRowData } from "./components/SymbolDetailDrawer";
import toast from "react-hot-toast";

export default function MobileApp() {
  const { accessToken, user, logout, isAdmin } = useAuthStore();
  const [activeTab, setActiveTab] = useState<MobileTab>("algo");

  const [theme, setTheme] = useState<"dark" | "light">(() => {
    return (localStorage.getItem("theme") as "dark" | "light") || "dark";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);

    // Synchronize native Android status bar colors and icons with theme
    try {
      if (Capacitor.isPluginAvailable("StatusBar")) {
        StatusBar.show().catch(() => {});
        StatusBar.setOverlaysWebView({ overlay: false }).catch(() => {});
        if (theme === "dark") {
          StatusBar.setStyle({ style: Style.Dark }).catch(() => {});
          StatusBar.setBackgroundColor({ color: "#0B1933" }).catch(() => {});
        } else {
          StatusBar.setStyle({ style: Style.Light }).catch(() => {});
          StatusBar.setBackgroundColor({ color: "#f4f7fa" }).catch(() => {});
        }
      }
    } catch {}
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const [algoRows, setAlgoRows] = useState<AlgoRowData[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistRowData[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [wsStatus, setWsStatus] = useState<"live" | "connecting" | "polling">("connecting");
  const [wsLatencyMs, setWsLatencyMs] = useState<number | null>(null);
  const [dhanActive, setDhanActive] = useState(true);

  const wsRef = useRef<WebSocket | null>(null);
  const pingStartRef = useRef<number>(Date.now());
  const seenAlertIds = useRef<Set<string>>(new Set());

  // 1. Fetch Algo Rows
  const fetchAlgoRows = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await api.get("/terminal/algo-rows");
      setAlgoRows(res.data?.rows || res.data || []);
    } catch (err) {
      console.error("Failed to fetch algo rows", err);
    }
  }, [accessToken]);

  // 2. Fetch Watchlist Rows
  const fetchWatchlist = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await api.get("/terminal/watchlist-rows");
      setWatchlist(Array.isArray(res.data) ? res.data : res.data?.rows || []);
    } catch (err) {
      console.error("Failed to fetch watchlist", err);
    }
  }, [accessToken]);

  // 3. Initial Snapshot Load
  useEffect(() => {
    if (!accessToken) {
      setIsLoading(false);
      return;
    }
    Promise.all([fetchAlgoRows(), fetchWatchlist()]).finally(() => {
      setIsLoading(false);
    });
  }, [accessToken, fetchAlgoRows, fetchWatchlist]);

  // 4. Background Tab Visibility Reconnection (Instant State Reconcile)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible" && accessToken) {
        fetchAlgoRows();
        fetchWatchlist();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleVisibilityChange);
    };
  }, [accessToken, fetchAlgoRows, fetchWatchlist]);

  // 5. Live WebSocket Feed
  useEffect(() => {
    if (!accessToken) return;
    const url = `${wsBase()}/api/ws/market?token=${accessToken}&symbols=ALL`;

    let reconnectTimer: any = null;

    function connect() {
      setWsStatus("connecting");
      pingStartRef.current = Date.now();

      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsStatus("live");
          const rtt = Math.max(12, Math.min(180, Date.now() - pingStartRef.current));
          setWsLatencyMs(rtt);
        };

        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            let ticks: any[] = [];
            if (msg.type === "ticks") {
              if (Array.isArray(msg.data)) {
                ticks = msg.data;
              } else if (msg.data && typeof msg.data === "object") {
                ticks = Object.values(msg.data);
              }
            }
            if (ticks.length > 0) {
              const tickMap: Record<string, any> = {};
              ticks.forEach((t: any) => {
                if (t.symbol) tickMap[t.symbol] = t;
              });

              // Update Algo Rows live LTP & calculations
              setAlgoRows((prev) =>
                prev.map((r) => {
                  const tick = tickMap[r.symbol];
                  if (!tick) return r;
                  const liveLtp = parseFloat(tick.ltp) || r.live_ltp;
                  let pnl = r.pnl;
                  if (r.status === "IN_POSITION" && r.buy_price) {
                    pnl = Math.round((liveLtp - r.buy_price) * r.quantity * 100) / 100;
                  }
                  return { ...r, live_ltp: liveLtp, pnl };
                })
              );

              // Update Watchlist rows live prices
              setWatchlist((prev) =>
                prev.map((w) => {
                  const tick = tickMap[w.symbol];
                  if (!tick) return w;
                  const liveLtp = parseFloat(tick.ltp) || w.ltp || 0;
                  const pClose = w.p_close || tick.close || liveLtp;
                  const change = Math.round((liveLtp - pClose) * 100) / 100;
                  const changePct = pClose > 0 ? Math.round((change / pClose) * 10000) / 100 : 0;
                  return {
                    ...w,
                    ltp: liveLtp,
                    open: parseFloat(tick.open) || w.open,
                    high: parseFloat(tick.high) || w.high,
                    low: parseFloat(tick.low) || w.low,
                    vwap: parseFloat(tick.vwap || tick.atp) || w.vwap,
                    volume: parseInt(tick.volume) || w.volume,
                    change,
                    change_pct: changePct,
                  };
                })
              );
            }
          } catch {}
        };

        ws.onerror = () => {
          setWsStatus("polling");
        };

        ws.onclose = () => {
          setWsStatus("polling");
          reconnectTimer = setTimeout(connect, 6000);
        };
      } catch (err) {
        setWsStatus("polling");
        reconnectTimer = setTimeout(connect, 6000);
      }
    }

    connect();

    // REST Polling fallback interval: sync both algo rows and watchlist every 3 seconds
    const pollInterval = setInterval(() => {
      fetchAlgoRows();
      fetchWatchlist();
    }, 3000);

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(pollInterval);
      wsRef.current?.close();
    };
  }, [accessToken, fetchAlgoRows]);

  // 6. Broker Alerts & Notifications Watcher
  useEffect(() => {
    if (!accessToken) return;
    const alertInterval = setInterval(async () => {
      try {
        const res = await api.get("/terminal/alerts");
        const alerts = res.data?.alerts || [];
        alerts.forEach((alert: any) => {
          const key = `${alert.title}-${alert.time}`;
          if (!seenAlertIds.current.has(key)) {
            seenAlertIds.current.add(key);
            if (alert.severity === "error") {
              toast.error(`${alert.title}: ${alert.message}`, { duration: 6000 });
            } else {
              toast(`${alert.title}: ${alert.message}`);
            }
          }
        });
      } catch {}
    }, 5000);

    return () => clearInterval(alertInterval);
  }, [accessToken]);

  // If not authenticated, render mobile login page
  if (!accessToken) {
    return (
      <MobileLoginPage
        theme={theme}
        onToggleTheme={toggleTheme}
        onLoginSuccess={() => fetchAlgoRows()}
      />
    );
  }

  // Admin Execution Handlers
  const handleToggleActive = async (rowId: string, currentActive: boolean) => {
    try {
      await api.patch(`/terminal/algo-rows/${rowId}`, {
        is_algo_active: !currentActive,
      });
      toast.success(!currentActive ? "Algo Activated (ON)" : "Algo Deactivated (OFF)");
      fetchAlgoRows();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to toggle algo");
    }
  };

  const handleManualOrder = async (rowId: string, side: "BUY" | "SELL") => {
    try {
      const res = await api.post(`/terminal/algo-rows/${rowId}/manual-order`, { side });
      toast.success(res.data?.detail || `Manual ${side} order executed!`);
      fetchAlgoRows();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || `Manual ${side} order rejected`);
    }
  };

  const handleKill = async (rowId: string) => {
    try {
      await api.post(`/terminal/algo-rows/${rowId}/kill`);
      toast.error("EMERGENCY KILL SWITCH: Position squared off!");
      fetchAlgoRows();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to execute kill switch");
    }
  };

  const handleSaveConfig = async (rowId: string, payload: any) => {
    try {
      await api.patch(`/terminal/algo-rows/${rowId}`, payload);
      toast.success("Parameters updated successfully");
      fetchAlgoRows();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to update parameters");
    }
  };

  const handleReset = async (rowId: string) => {
    try {
      await api.post(`/terminal/algo-rows/${rowId}/reset`);
      toast.success("Trade cycle counter reset to 0");
      fetchAlgoRows();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to reset cycle");
    }
  };

  const handleDelete = async (rowId: string) => {
    try {
      await api.delete(`/terminal/algo-rows/${rowId}`);
      toast.success("Script removed from Algo Window");
      fetchAlgoRows();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to delete script");
    }
  };

  const handleAddToAlgo = async (item: WatchlistRowData) => {
    try {
      await api.post("/terminal/algo-rows", {
        symbol: item.symbol,
        exchange: item.exchange || "NSE",
        segment: item.segment || "NSE_EQ",
        token: item.token,
        quantity: 25,
        number_of_trades: 1,
        target_type: "T1",
        trade_mode: "FULL",
      });
      toast.success(`Added ${item.symbol} to Algo Window!`);
      await fetchAlgoRows();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to add to Algo Window");
    }
  };

  const handleAddToWatchlist = async (inst: any) => {
    try {
      await api.post("/market/watchlist", {
        symbol: inst.symbol,
        security_id: String(inst.security_id || inst.token || "0"),
        exchange_segment: inst.exchange_segment || inst.segment || "NSE_EQ",
      });
      await fetchWatchlist();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to add symbol");
      throw err;
    }
  };

  const handleRemoveFromWatchlist = async (idOrSymbol: string) => {
    try {
      const target = watchlist.find((w) => w.id === idOrSymbol || w.symbol === idOrSymbol)?.symbol || idOrSymbol;
      await api.delete(`/market/watchlist/${encodeURIComponent(target)}`);
      toast.success(`Removed ${target} from watchlist`);
      await fetchWatchlist();
    } catch (err: any) {
      toast.error("Failed to remove symbol");
    }
  };

  // Calculations
  const totalPnl = algoRows.reduce((acc, r) => acc + (r.pnl || 0), 0);
  const activeAlgoCount = algoRows.filter((r) => r.is_algo_active).length;
  const userIsAdmin = isAdmin();

  return (
    <div className="mobile-app-shell select-none">
      {/* Sticky Top Header */}
      <MobileHeader
        userEmail={user?.username || user?.email || "Trader"}
        isAdmin={userIsAdmin}
        totalPnl={totalPnl}
        activeAlgoCount={activeAlgoCount}
        wsLatencyMs={wsLatencyMs}
        wsStatus={wsStatus}
        dhanActive={dhanActive}
        theme={theme}
        onToggleTheme={toggleTheme}
        onLogout={logout}
      />

      {/* Main Tab Content */}
      <main className="flex-1 overflow-y-auto">
        {activeTab === "algo" ? (
          <MobileAlgoPage
            rows={algoRows}
            isAdmin={userIsAdmin}
            onRefresh={fetchAlgoRows}
            onToggleActive={handleToggleActive}
            onManualOrder={handleManualOrder}
            onKill={handleKill}
            onSaveConfig={handleSaveConfig}
            onReset={handleReset}
            onDelete={handleDelete}
            onNavigateToWatchlist={() => setActiveTab("watchlist")}
          />
        ) : activeTab === "watchlist" ? (
          <MobileWatchlistPage
            watchlist={watchlist}
            isAdmin={userIsAdmin}
            onRefresh={fetchWatchlist}
            onAddToAlgo={handleAddToAlgo}
            onAddToWatchlist={handleAddToWatchlist}
            onRemoveFromWatchlist={handleRemoveFromWatchlist}
          />
        ) : (
          <MobileAstroPage />
        )}
      </main>

      {/* Docked Bottom Navigation */}
      <MobileBottomNav
        currentTab={activeTab}
        onChangeTab={setActiveTab}
        activeAlgoCount={activeAlgoCount}
        watchlistCount={watchlist.length}
      />
    </div>
  );
}
