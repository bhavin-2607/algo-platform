import React, { useState, useMemo } from "react";
import { Search, Zap, Plus, Filter } from "lucide-react";
import { AlgoSmartCard, AlgoRowData } from "../components/AlgoSmartCard";
import { AlgoConfigDrawer } from "../components/AlgoConfigDrawer";
import toast from "react-hot-toast";

interface MobileAlgoPageProps {
  rows: AlgoRowData[];
  isAdmin: boolean;
  onRefresh: () => Promise<void>;
  onToggleActive: (rowId: string, currentActive: boolean) => Promise<void>;
  onManualOrder: (rowId: string, side: "BUY" | "SELL") => Promise<void>;
  onKill: (rowId: string) => Promise<void>;
  onSaveConfig: (rowId: string, payload: any) => Promise<void>;
  onReset: (rowId: string) => Promise<void>;
  onDelete: (rowId: string) => Promise<void>;
  onNavigateToWatchlist: () => void;
}

type FilterTab = "ALL" | "ACTIVE" | "IN_POSITION" | "IDLE";

export const MobileAlgoPage: React.FC<MobileAlgoPageProps> = ({
  rows,
  isAdmin,
  onRefresh,
  onToggleActive,
  onManualOrder,
  onKill,
  onSaveConfig,
  onReset,
  onDelete,
  onNavigateToWatchlist,
}) => {
  const [filterTab, setFilterTab] = useState<FilterTab>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [configRow, setConfigRow] = useState<AlgoRowData | null>(null);

  // Filter calculations
  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        if (!r.symbol.toLowerCase().includes(q)) return false;
      }
      // Tab filter
      if (filterTab === "ACTIVE") return r.is_algo_active;
      if (filterTab === "IN_POSITION") return r.status === "IN_POSITION";
      if (filterTab === "IDLE") return r.status === "IDLE" || !r.is_algo_active;
      return true;
    });
  }, [rows, filterTab, searchQuery]);

  const activeCount = rows.filter((r) => r.is_algo_active).length;
  const inPositionCount = rows.filter((r) => r.status === "IN_POSITION").length;
  const idleCount = rows.filter((r) => r.status === "IDLE").length;

  return (
    <div className="space-y-3 pb-24 px-3 pt-2">
      {/* Search & Filter Strip */}
      <div className="flex items-center space-x-2">
        <div className="flex-1 relative">
          <Search size={15} className="absolute left-3 top-2.5" style={{ color: "var(--muted)" }} />
          <input
            type="text"
            placeholder="Search algo symbols..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-9 pl-9 pr-3 rounded-xl text-xs focus:outline-hidden"
            style={{
              background: "var(--surface2)",
              border: "1px solid var(--border)",
              color: "var(--text)",
            }}
          />
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center space-x-1.5 overflow-x-auto pb-1 no-scrollbar text-xs">
        {[
          { id: "ALL", label: "All", count: rows.length },
          { id: "ACTIVE", label: "Active ON", count: activeCount },
          { id: "IN_POSITION", label: "In Position", count: inPositionCount },
          { id: "IDLE", label: "Idle / Off", count: idleCount },
        ].map((tab) => (
          <button
            type="button"
            key={tab.id}
            onClick={() => setFilterTab(tab.id as FilterTab)}
            className="px-3 py-1.5 rounded-xl font-semibold whitespace-nowrap transition-all flex items-center space-x-1.5 active:scale-95 shadow-xs"
            style={{
              background: filterTab === tab.id ? "var(--green)" : "var(--surface2)",
              color: filterTab === tab.id ? "var(--bg)" : "var(--muted)",
              border: filterTab === tab.id ? "none" : "1px solid var(--border)",
            }}
          >
            <span>{tab.label}</span>
            <span
              className="text-[10px] px-1.5 py-0.2 rounded-full font-mono"
              style={{
                background: filterTab === tab.id ? "rgba(0, 0, 0, 0.2)" : "var(--surface)",
                color: filterTab === tab.id ? "inherit" : "var(--text)",
              }}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Rows List */}
      {filteredRows.length > 0 ? (
        <div className="space-y-3">
          {filteredRows.map((row) => (
            <AlgoSmartCard
              key={row.id}
              row={row}
              isAdmin={isAdmin}
              onToggleActive={onToggleActive}
              onManualOrder={onManualOrder}
              onKill={onKill}
              onOpenConfig={(r) => setConfigRow(r)}
            />
          ))}
        </div>
      ) : (
        <div
          className="rounded-2xl p-8 text-center space-y-4 my-6"
          style={{ background: "var(--surface)", border: "1px dashed var(--border)" }}
        >
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center mx-auto"
            style={{ background: "var(--surface2)", color: "var(--muted)" }}
          >
            <Zap size={24} />
          </div>
          <div>
            <h4 className="text-sm font-bold" style={{ color: "var(--text)" }}>No Algo Scripts Found</h4>
            <p className="text-xs mt-1 max-w-xs mx-auto" style={{ color: "var(--muted)" }}>
              {searchQuery
                ? "No scripts match your search query."
                : "Add symbols from the Watchlist to start automated execution."}
            </p>
          </div>
          <button
            onClick={onNavigateToWatchlist}
            className="inline-flex items-center space-x-1.5 px-4 py-2 text-xs font-bold rounded-xl active:scale-95 shadow-md transition-all"
            style={{ background: "var(--green)", color: "var(--bg)" }}
          >
            <Plus size={15} />
            <span>Go to Watchlist</span>
          </button>
        </div>
      )}

      {/* Config Drawer */}
      <AlgoConfigDrawer
        row={configRow}
        isOpen={Boolean(configRow)}
        onClose={() => setConfigRow(null)}
        onSave={onSaveConfig}
        onReset={onReset}
        onDelete={onDelete}
      />
    </div>
  );
};
