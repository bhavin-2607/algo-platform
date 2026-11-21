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
          <Search size={15} className="absolute left-3 top-2.5 text-zinc-500" />
          <input
            type="text"
            placeholder="Search algo symbols..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-9 pl-9 pr-3 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-hidden"
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
            key={tab.id}
            onClick={() => setFilterTab(tab.id as FilterTab)}
            className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition-all flex items-center space-x-1.5 ${
              filterTab === tab.id
                ? "bg-emerald-600 text-white font-bold shadow-xs"
                : "bg-zinc-900 text-zinc-400 hover:text-zinc-200 border border-zinc-800/80"
            }`}
          >
            <span>{tab.label}</span>
            <span
              className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                filterTab === tab.id ? "bg-emerald-800 text-white" : "bg-zinc-800 text-zinc-400"
              }`}
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
        <div className="bg-zinc-900/60 border border-dashed border-zinc-800 rounded-2xl p-8 text-center space-y-4 my-6">
          <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center mx-auto text-zinc-500">
            <Zap size={24} />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white">No Algo Scripts Found</h4>
            <p className="text-xs text-zinc-400 mt-1 max-w-xs mx-auto">
              {searchQuery
                ? "No scripts match your search query."
                : "Add symbols from the Watchlist to start automated execution."}
            </p>
          </div>
          <button
            onClick={onNavigateToWatchlist}
            className="inline-flex items-center space-x-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl active:scale-95 shadow-md transition-all"
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
