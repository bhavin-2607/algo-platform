import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";
import {
  Compass,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  MapPin,
  Clock,
  Info,
  HelpCircle,
  X,
  Layers,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import {
  getAstroSettings,
  saveAstroSettings,
  AstroTimingSettings,
} from "@/utils/astroSettings";
import {
  AstroMarketSignal,
  IntradayAstroResponse,
  MarketWeekOutlookResponse,
  MarketDayOutlookItem,
} from "@/components/astro/AstroPivotDrawer";

export const MobileAstroPage: React.FC = () => {
  const [settings, setSettings] = useState<AstroTimingSettings>(getAstroSettings);
  const [timeMode, setTimeMode] = useState<"SUNRISE" | "09:00" | "LIVE">("SUNRISE");
  const [activeTab, setActiveTab] = useState<"TIMELINE" | "ASPECTS" | "EPHEMERIS">("EPHEMERIS");
  const [showTrendGuide, setShowTrendGuide] = useState<boolean>(false);

  const [isDaysCollapsed, setIsDaysCollapsed] = useState<boolean>(() => {
    return settings.marketDaysCollapsed ?? false;
  });

  // Listen for settings updates from other components
  useEffect(() => {
    const handleSettingsUpdated = (e: any) => {
      if (e?.detail) setSettings(e.detail);
    };
    window.addEventListener("astro_settings_updated", handleSettingsUpdated);
    return () => window.removeEventListener("astro_settings_updated", handleSettingsUpdated);
  }, []);

  const toggleDaysCollapse = () => {
    const nextVal = !isDaysCollapsed;
    setIsDaysCollapsed(nextVal);
    const nextSettings = { ...settings, marketDaysCollapsed: nextVal };
    setSettings(nextSettings);
    saveAstroSettings(nextSettings);
  };

  const todayDate = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }, []);

  const [selectedDate, setSelectedDate] = useState<string>(todayDate);
  const isSelectedToday = selectedDate === todayDate;

  // Multi-week market outlook query
  const outlookTimeMode = timeMode === "09:00" ? "09:00" : "SUNRISE";
  const { data: weekData, isLoading: weekLoading } = useQuery<MarketWeekOutlookResponse>({
    queryKey: [
      "astro-market-week-outlook",
      settings.includePreviousWeek,
      settings.includeNextWeek,
      todayDate,
      outlookTimeMode,
      settings.latitude,
      settings.longitude,
      settings.city,
    ],
    queryFn: async () => {
      const res = await api.get(
        `/v1/astro/market-week-outlook?include_prev=${settings.includePreviousWeek}&include_next=${settings.includeNextWeek}&ref_date_str=${todayDate}&time_mode=${outlookTimeMode}&lat=${settings.latitude}&lon=${settings.longitude}&city=${encodeURIComponent(settings.city)}`
      );
      return res.data;
    },
    staleTime: 60000,
  });

  // Intraday shift windows query
  const { data: windowsData, isLoading: windowsLoading } = useQuery<IntradayAstroResponse>({
    queryKey: ["astro-intraday-windows", selectedDate],
    queryFn: async () => {
      const res = await api.get(`/v1/astro/intraday-windows?date_str=${selectedDate}`);
      return res.data;
    },
    enabled: !!selectedDate,
    staleTime: 60000,
  });

  // Snapshot telemetry for selected trading day
  const { data: selectedDaySnapshot, isLoading: snapshotLoading } = useQuery<AstroMarketSignal>({
    queryKey: [
      "astro-snapshot-day",
      selectedDate,
      timeMode,
      settings.latitude,
      settings.longitude,
      settings.city,
    ],
    queryFn: async () => {
      const res = await api.get(
        `/v1/astro/snapshot?date_str=${selectedDate}&time_mode=${timeMode}&lat=${settings.latitude}&lon=${settings.longitude}&city=${encodeURIComponent(settings.city)}`
      );
      return res.data;
    },
    enabled: !!selectedDate,
    staleTime: 60000,
  });

  const activeSignal = selectedDaySnapshot;

  const tradingDays = weekData?.days ?? [];
  const currentDayIndex = tradingDays.findIndex((d) => d.date === selectedDate);

  const handlePrevDay = () => {
    if (currentDayIndex > 0) {
      setSelectedDate(tradingDays[currentDayIndex - 1].date);
    }
  };

  const handleNextDay = () => {
    if (currentDayIndex >= 0 && currentDayIndex < tradingDays.length - 1) {
      setSelectedDate(tradingDays[currentDayIndex + 1].date);
    }
  };

  const isVol = activeSignal?.volatility_alert;
  const isBullish = activeSignal?.regime_bias === "BULLISH_TAILWIND";
  const isBearish = activeSignal?.regime_bias === "BEARISH_HEADWIND";

  const prevWeekDays = tradingDays.filter((d) => d.week_category === "PREVIOUS_WEEK");
  const currWeekDays = tradingDays.filter((d) => d.week_category === "CURRENT_WEEK");
  const nextWeekDays = tradingDays.filter((d) => d.week_category === "NEXT_WEEK");

  const activeSunriseDisplay = activeSignal?.sunrise_time_iso
    ? `${activeSignal.sunrise_time_iso.slice(11, 16)} IST`
    : "~06:58 IST";

  return (
    <div className="space-y-3 pb-24 px-3 pt-2 select-none">
      {/* Mobile Header Bar */}
      <div
        className="p-3 rounded-xl flex items-center justify-between"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center space-x-2">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{
              background: isVol
                ? "rgba(255,59,87,0.15)"
                : isBullish
                ? "rgba(0,230,118,0.15)"
                : isBearish
                ? "rgba(255,183,3,0.15)"
                : "rgba(8,182,222,0.15)",
              color: isVol
                ? "var(--red)"
                : isBullish
                ? "var(--green)"
                : isBearish
                ? "var(--yellow)"
                : "var(--ba-cyan)",
            }}
          >
            <Compass size={16} />
          </div>
          <div>
            <div className="flex items-center space-x-1.5">
              <span className="text-xs font-extrabold tracking-tight" style={{ color: "var(--text)" }}>
                ASTRO TREND & CYCLES
              </span>
              <span
                className="text-[9px] font-bold px-1.5 py-0.2 rounded"
                style={{ background: "rgba(255,255,255,0.08)", color: "var(--muted)" }}
              >
                WATCH ONLY
              </span>
            </div>
            <div className="text-[10px] mt-0.5 flex items-center space-x-1" style={{ color: "var(--muted)" }}>
              <MapPin size={9} style={{ color: "var(--ba-cyan)" }} />
              <span>{settings.city} ({settings.latitude.toFixed(2)}°N, {settings.longitude.toFixed(2)}°E)</span>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowTrendGuide((prev) => !prev)}
          className="text-[10px] font-bold px-2 py-1 rounded-md flex items-center space-x-1 active:scale-95 transition-all"
          style={{
            background: showTrendGuide ? "rgba(8,182,222,0.2)" : "var(--surface2)",
            color: showTrendGuide ? "var(--ba-cyan)" : "var(--muted)",
            border: `1px solid ${showTrendGuide ? "rgba(8,182,222,0.4)" : "var(--border)"}`,
          }}
        >
          <HelpCircle size={11} />
          <span>GUIDE</span>
        </button>
      </div>

      {/* Trend Guide Collapsible Card */}
      {showTrendGuide && (
        <div
          className="p-3 rounded-xl text-xs space-y-2"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            color: "var(--text)",
          }}
        >
          <div className="flex items-center justify-between">
            <span className="font-extrabold text-[11px] tracking-tight" style={{ color: "var(--ba-cyan)" }}>
              HOW TO IDENTIFY THE MARKET TREND
            </span>
            <button
              type="button"
              onClick={() => setShowTrendGuide(false)}
              className="text-[10px]"
              style={{ color: "var(--muted)" }}
            >
              <X size={13} />
            </button>
          </div>

          <div className="space-y-1.5 text-[10px] leading-relaxed" style={{ color: "var(--muted)" }}>
            <div className="p-2 rounded-lg" style={{ background: "var(--surface2)" }}>
              <strong style={{ color: "var(--green)" }}>BULLISH TAILWIND (Score &ge; +0.8):</strong> Harmonic trines/sextiles dominate. Momentum favors buying dips.
            </div>
            <div className="p-2 rounded-lg" style={{ background: "var(--surface2)" }}>
              <strong style={{ color: "var(--yellow)" }}>BEARISH HEADWIND (Score &le; -0.8):</strong> Resistance aspects dominate. Rallies face selling pressure.
            </div>
            <div className="p-2 rounded-lg" style={{ background: "var(--surface2)" }}>
              <strong style={{ color: "var(--red)" }}>HIGH VOLATILITY:</strong> Hard aspects &ge; 1.8 or stationary turning planets. Expect sharp two-way whipsaws.
            </div>
            <div className="p-2 rounded-lg" style={{ background: "var(--surface2)" }}>
              <strong style={{ color: "var(--text)" }}>Price Confirmation:</strong> Confirm with VWAP & EMA 20/50 before entering BSA trades.
            </div>
          </div>
        </div>
      )}

      {/* Market Trading Days Collapsible Strip */}
      <div
        className="rounded-xl overflow-hidden transition-all"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
        }}
      >
        {/* Strip Header Row */}
        <div className="p-2.5 flex items-center justify-between">
          <div className="flex items-center space-x-1.5">
            <span className="text-[11px] font-extrabold tracking-tight" style={{ color: "var(--text)" }}>
              MARKET DAYS
            </span>
            <span
              className="text-[9px] font-bold px-1.5 py-0.2 rounded"
              style={{
                background:
                  selectedDate === todayDate
                    ? "rgba(0, 230, 118, 0.15)"
                    : selectedDate < todayDate
                    ? "rgba(255, 183, 3, 0.15)"
                    : "rgba(8, 182, 222, 0.15)",
                color:
                  selectedDate === todayDate
                    ? "var(--green)"
                    : selectedDate < todayDate
                    ? "var(--yellow)"
                    : "var(--ba-cyan)",
              }}
            >
              {selectedDate === todayDate ? "TODAY" : selectedDate < todayDate ? "AUDIT" : "PROJ"}
            </span>
            {isDaysCollapsed && (
              <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                {selectedDate.slice(5)}
              </span>
            )}
          </div>

          <div className="flex items-center space-x-1.5">
            {/* Stepper Navigation */}
            <button
              type="button"
              onClick={handlePrevDay}
              disabled={currentDayIndex <= 0}
              className="p-1 rounded bg-transparent"
              style={{
                color: currentDayIndex > 0 ? "var(--text)" : "var(--muted)",
                border: "1px solid var(--border)",
              }}
              title="Previous Day"
            >
              <ChevronLeft size={12} />
            </button>

            <button
              type="button"
              onClick={() => setSelectedDate(todayDate)}
              className="text-[10px] font-extrabold px-2 py-0.5 rounded"
              style={{
                background: selectedDate === todayDate ? "var(--ba-cyan)" : "var(--surface2)",
                color: selectedDate === todayDate ? "#000" : "var(--text)",
                border: `1px solid ${selectedDate === todayDate ? "var(--ba-cyan)" : "var(--border)"}`,
              }}
            >
              TODAY
            </button>

            <button
              type="button"
              onClick={handleNextDay}
              disabled={currentDayIndex < 0 || currentDayIndex >= tradingDays.length - 1}
              className="p-1 rounded bg-transparent"
              style={{
                color:
                  currentDayIndex >= 0 && currentDayIndex < tradingDays.length - 1
                    ? "var(--text)"
                    : "var(--muted)",
                border: "1px solid var(--border)",
              }}
              title="Next Day"
            >
              <ChevronRight size={12} />
            </button>

            {/* Collapse / Expand Toggle */}
            <button
              type="button"
              onClick={toggleDaysCollapse}
              className="text-[10px] font-bold px-2 py-0.5 rounded flex items-center space-x-1 active:scale-95"
              style={{
                background: isDaysCollapsed ? "rgba(8,182,222,0.15)" : "var(--surface2)",
                color: isDaysCollapsed ? "var(--ba-cyan)" : "var(--muted)",
                border: `1px solid ${isDaysCollapsed ? "rgba(8,182,222,0.4)" : "var(--border)"}`,
              }}
              title={isDaysCollapsed ? "Expand days strip" : "Collapse days strip to expand Grid"}
            >
              {isDaysCollapsed ? <ChevronDown size={11} /> : <ChevronUp size={11} />}
              <span>{isDaysCollapsed ? "EXPAND" : "COLLAPSE"}</span>
            </button>
          </div>
        </div>

        {/* Horizontal Days Strip (Collapsible) */}
        {!isDaysCollapsed && (
          <div className="px-2.5 pb-2.5 flex items-center space-x-2 overflow-x-auto no-scrollbar">
            {weekLoading && (
              <div className="text-[10px] py-2" style={{ color: "var(--muted)" }}>
                Calculating market cycles...
              </div>
            )}

            {/* Render Current Week Days */}
            {currWeekDays.map((day) => renderMobileDayChip(day, selectedDate, setSelectedDate))}

            {/* Render Next Week Days */}
            {nextWeekDays.map((day) => renderMobileDayChip(day, selectedDate, setSelectedDate))}
          </div>
        )}
      </div>

      {/* Benchmark Time Selector Strip */}
      <div
        className="p-2.5 rounded-xl flex items-center justify-between"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
        }}
      >
        <span className="text-[10px] font-extrabold uppercase" style={{ color: "var(--muted)" }}>
          TIME BENCHMARK:
        </span>
        <div className="flex items-center space-x-1.5">
          <button
            type="button"
            onClick={() => setTimeMode("SUNRISE")}
            className="text-[10px] font-bold px-2.5 py-1 rounded"
            style={{
              background: timeMode === "SUNRISE" ? "var(--ba-cyan)" : "var(--surface2)",
              color: timeMode === "SUNRISE" ? "#000" : "var(--muted)",
              border: `1px solid ${timeMode === "SUNRISE" ? "var(--ba-cyan)" : "var(--border)"}`,
            }}
          >
            SUNRISE ({activeSunriseDisplay.slice(0, 5)})
          </button>

          <button
            type="button"
            onClick={() => setTimeMode("09:00")}
            className="text-[10px] font-bold px-2.5 py-1 rounded"
            style={{
              background: timeMode === "09:00" ? "var(--ba-cyan)" : "var(--surface2)",
              color: timeMode === "09:00" ? "#000" : "var(--muted)",
              border: `1px solid ${timeMode === "09:00" ? "var(--ba-cyan)" : "var(--border)"}`,
            }}
          >
            09:00 AM
          </button>

          {isSelectedToday && (
            <button
              type="button"
              onClick={() => setTimeMode("LIVE")}
              className="text-[10px] font-bold px-2.5 py-1 rounded"
              style={{
                background: timeMode === "LIVE" ? "var(--green)" : "var(--surface2)",
                color: timeMode === "LIVE" ? "#000" : "var(--muted)",
                border: `1px solid ${timeMode === "LIVE" ? "var(--green)" : "var(--border)"}`,
              }}
            >
              LIVE
            </button>
          )}
        </div>
      </div>

      {/* Real-time Summary Cards Strip */}
      {activeSignal && (
        <div className="grid grid-cols-3 gap-2">
          {/* Regime Bias */}
          <div
            className="p-2.5 rounded-xl space-y-1"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <div className="text-[9px] font-bold uppercase" style={{ color: "var(--muted)" }}>
              REGIME BIAS
            </div>
            <div
              className="text-[11px] font-extrabold flex items-center space-x-1"
              style={{
                color: isVol
                  ? "var(--red)"
                  : isBullish
                  ? "var(--green)"
                  : isBearish
                  ? "var(--yellow)"
                  : "var(--text)",
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full inline-block"
                style={{
                  background: isVol
                    ? "var(--red)"
                    : isBullish
                    ? "var(--green)"
                    : isBearish
                    ? "var(--yellow)"
                    : "var(--muted)",
                }}
              />
              <span className="truncate">
                {activeSignal.regime_bias === "HIGH_VOLATILITY_CAUTION"
                  ? "VOLATILE"
                  : activeSignal.regime_bias === "BULLISH_TAILWIND"
                  ? "BULLISH"
                  : activeSignal.regime_bias === "BEARISH_HEADWIND"
                  ? "BEARISH"
                  : "NEUTRAL"}
              </span>
            </div>
          </div>

          {/* Aspect Score */}
          <div
            className="p-2.5 rounded-xl space-y-1"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <div className="text-[9px] font-bold uppercase" style={{ color: "var(--muted)" }}>
              ASPECT SCORE
            </div>
            <div
              className="text-[12px] font-mono font-extrabold"
              style={{
                color:
                  activeSignal.net_sentiment_score > 0
                    ? "var(--green)"
                    : activeSignal.net_sentiment_score < 0
                    ? "var(--red)"
                    : "var(--text)",
              }}
            >
              {activeSignal.net_sentiment_score > 0
                ? `+${activeSignal.net_sentiment_score}`
                : activeSignal.net_sentiment_score}
            </div>
          </div>

          {/* Moon Nakshatra & Sub */}
          <div
            className="p-2.5 rounded-xl space-y-1"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <div className="text-[9px] font-bold uppercase" style={{ color: "var(--muted)" }}>
              MOON SUB
            </div>
            <div className="text-[11px] font-extrabold truncate" style={{ color: "var(--text)" }}>
              {activeSignal.moon_kp_sub_lord} Sub
            </div>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div
        className="flex items-center space-x-1 p-1 rounded-xl"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        {[
          { id: "EPHEMERIS", label: `EPHEMERIS (${activeSignal?.planets.length || 0})` },
          { id: "TIMELINE", label: `TIMELINE (${windowsData?.total_windows || 0})` },
          { id: "ASPECTS", label: `ASPECTS (${activeSignal?.active_aspects.length || 0})` },
        ].map((tab) => (
          <button
            type="button"
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className="flex-1 py-1.5 rounded-lg text-[10px] font-extrabold tracking-tight transition-all"
            style={{
              background: activeTab === tab.id ? "var(--ba-cyan)" : "transparent",
              color: activeTab === tab.id ? "#000" : "var(--muted)",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="space-y-2">
        {/* TAB 1: EPHEMERIS GRID */}
        {activeTab === "EPHEMERIS" && (
          <div
            className="p-3 rounded-xl overflow-x-auto"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            {snapshotLoading ? (
              <div className="text-center py-8 text-xs" style={{ color: "var(--muted)" }}>
                Loading ephemeris telemetry...
              </div>
            ) : activeSignal ? (
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr
                    className="text-[9px] uppercase font-bold border-b"
                    style={{ borderColor: "var(--border)", color: "var(--muted)" }}
                  >
                    <th className="py-1.5 px-2">Body</th>
                    <th className="py-1.5 px-2">Sign & Deg</th>
                    <th className="py-1.5 px-2">Nakshatra</th>
                    <th className="py-1.5 px-2">KP Sub</th>
                    <th className="py-1.5 px-2">Speed/Day</th>
                    <th className="py-1.5 px-2 text-right">State</th>
                  </tr>
                </thead>
                <tbody>
                  {activeSignal.planets.map((p, idx) => (
                    <tr
                      key={idx}
                      className="border-b text-[11px]"
                      style={{
                        borderColor: "rgba(255,255,255,0.04)",
                        background: idx % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                      }}
                    >
                      <td className="py-2 px-2 font-bold" style={{ color: "var(--text)" }}>
                        {p.name}
                      </td>
                      <td className="py-2 px-2 font-mono">
                        <span style={{ color: "var(--ba-cyan)", fontWeight: 700 }}>{p.sign}</span>{" "}
                        <span style={{ color: "var(--text)", fontSize: 10 }}>{p.sign_degree_str}</span>
                      </td>
                      <td className="py-2 px-2 font-semibold">
                        {p.nakshatra} <span className="text-[9px]" style={{ color: "var(--muted)" }}>P{p.pada}</span>
                      </td>
                      <td className="py-2 px-2 font-bold" style={{ color: "var(--ba-amber)" }}>
                        {p.kp_sub_lord}
                      </td>
                      <td className="py-2 px-2 font-mono text-[10px]" style={{ color: "var(--text)" }}>
                        {p.speed_str || `${p.speed.toFixed(2)}°/d`}
                      </td>
                      <td className="py-2 px-2 text-right">
                        {p.is_stationary ? (
                          <span className="text-[8px] font-extrabold px-1.5 py-0.5 rounded" style={{ background: "rgba(255,59,87,0.2)", color: "var(--red)" }}>
                            STAT
                          </span>
                        ) : p.is_retrograde ? (
                          <span className="text-[8px] font-extrabold px-1.5 py-0.5 rounded" style={{ background: "rgba(255,183,3,0.2)", color: "var(--yellow)" }}>
                            RETRO
                          </span>
                        ) : (
                          <span className="text-[8px] font-bold" style={{ color: "var(--muted)" }}>
                            DIR
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        )}

        {/* TAB 2: INTRADAY TIMELINE SHIFTS */}
        {activeTab === "TIMELINE" && (
          <div className="space-y-2">
            {windowsLoading ? (
              <div className="text-center py-8 text-xs" style={{ color: "var(--muted)" }}>
                Scanning NSE intraday shift windows...
              </div>
            ) : windowsData?.windows && windowsData.windows.length > 0 ? (
              windowsData.windows.map((w, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl flex items-center justify-between"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                >
                  <div className="flex items-center space-x-2.5">
                    <div
                      className="font-mono text-xs font-extrabold px-2 py-1 rounded"
                      style={{ background: "var(--surface2)", color: "var(--ba-cyan)" }}
                    >
                      {w.time_str}
                    </div>
                    <div>
                      <div className="text-[11px] font-bold" style={{ color: "var(--text)" }}>
                        {w.from_entity} &rarr; {w.to_entity}
                      </div>
                      <div className="text-[9px]" style={{ color: "var(--muted)" }}>
                        {w.event_type === "MOON_NAKSHATRA_SHIFT" ? "Nakshatra Shift" : "KP Sub-Lord Shift"}
                      </div>
                    </div>
                  </div>
                  <span
                    className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                    style={{
                      background:
                        w.weight === "HIGH"
                          ? "rgba(255,59,87,0.15)"
                          : "rgba(8,182,222,0.15)",
                      color: w.weight === "HIGH" ? "var(--red)" : "var(--ba-cyan)",
                    }}
                  >
                    {w.weight}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-xs" style={{ color: "var(--muted)" }}>
                No transitions during market session.
              </div>
            )}
          </div>
        )}

        {/* TAB 3: ASPECT RADAR */}
        {activeTab === "ASPECTS" && (
          <div className="space-y-2">
            {activeSignal?.active_aspects && activeSignal.active_aspects.length > 0 ? (
              activeSignal.active_aspects.map((a, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl flex items-center justify-between"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                >
                  <div>
                    <div className="text-[11px] font-bold" style={{ color: "var(--text)" }}>
                      {a.body_a} &bull; {a.aspect_type} &bull; {a.body_b}
                    </div>
                    <div className="text-[9px]" style={{ color: "var(--muted)" }}>
                      Orb: {a.orb_deg.toFixed(2)}° &bull; Angle: {a.target_deg}°
                    </div>
                  </div>
                  <span
                    className="text-[9px] font-bold px-1.5 py-0.5 rounded font-mono"
                    style={{
                      background: a.is_hard ? "rgba(255,59,87,0.15)" : "rgba(0,230,118,0.15)",
                      color: a.is_hard ? "var(--red)" : "var(--green)",
                    }}
                  >
                    {a.is_hard ? `HARD (-${a.weight.toFixed(1)})` : `SOFT (+${a.weight.toFixed(1)})`}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-xs" style={{ color: "var(--muted)" }}>
                No major aspects active within orb tolerance.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// Helper for mobile market day chips
function renderMobileDayChip(
  day: MarketDayOutlookItem,
  selectedDate: string,
  onSelect: (date: string) => void
) {
  const isSelected = selectedDate === day.date;
  const isVol = day.volatility_alert;
  const isBull = day.regime_bias === "BULLISH_TAILWIND";
  const isBear = day.regime_bias === "BEARISH_HEADWIND";

  const dotColor = isVol
    ? "var(--red)"
    : isBull
    ? "var(--green)"
    : isBear
    ? "var(--yellow)"
    : "var(--muted)";

  return (
    <button
      key={day.date}
      type="button"
      onClick={() => onSelect(day.date)}
      className="flex-shrink-0 flex flex-col items-center justify-center p-2 rounded-lg transition-all active:scale-95"
      style={{
        minWidth: 64,
        background: isSelected ? "var(--surface2)" : "var(--surface)",
        border: isSelected
          ? "1px solid var(--ba-cyan)"
          : day.is_today
          ? "1px solid rgba(0,230,118,0.4)"
          : "1px solid var(--border)",
        boxShadow: isSelected ? "0 0 8px rgba(8, 182, 222, 0.25)" : "none",
      }}
    >
      <div className="flex items-center space-x-1">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: dotColor }} />
        <span
          className="text-[10px] font-bold"
          style={{ color: isSelected ? "var(--ba-cyan)" : "var(--text)" }}
        >
          {day.day_name} {day.date.slice(5)}
        </span>
      </div>

      <div
        className="text-[10px] font-mono font-extrabold mt-1"
        style={{
          color:
            day.net_sentiment_score > 0
              ? "var(--green)"
              : day.net_sentiment_score < 0
              ? "var(--red)"
              : "var(--muted)",
        }}
      >
        {day.net_sentiment_score > 0 ? `+${day.net_sentiment_score}` : day.net_sentiment_score}
      </div>
    </button>
  );
}
