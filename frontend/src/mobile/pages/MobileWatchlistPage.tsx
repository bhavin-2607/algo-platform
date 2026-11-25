import React, { useState, useEffect, useMemo } from "react";
import { Search, Plus, ListOrdered, Check, Loader2 } from "lucide-react";
import { WatchlistCard } from "../components/WatchlistCard";
import { SymbolDetailDrawer, WatchlistRowData } from "../components/SymbolDetailDrawer";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

interface InstrumentResult {
  symbol: string;
  name?: string;
  exchange: string;
  segment: string;
  token?: string;
  security_id?: string;
}

interface MobileWatchlistPageProps {
  watchlist: WatchlistRowData[];
  isAdmin: boolean;
  onRefresh: () => Promise<void>;
  onAddToAlgo: (item: WatchlistRowData) => Promise<void>;
  onAddToWatchlist: (instrument: InstrumentResult) => Promise<void>;
  onRemoveFromWatchlist: (id: string) => Promise<void>;
  onOpenOrder?: (item: WatchlistRowData, side: "BUY" | "SELL") => void;
}

export const MobileWatchlistPage: React.FC<MobileWatchlistPageProps> = ({
  watchlist,
  isAdmin,
  onRefresh,
  onAddToAlgo,
  onAddToWatchlist,
  onRemoveFromWatchlist,
  onOpenOrder,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<InstrumentResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedItem, setSelectedItem] = useState<WatchlistRowData | null>(null);

  // Debounced search on Dhan instruments
  useEffect(() => {
    if (!searchQuery || searchQuery.trim().length < 2) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await api.get("/market/instruments/search", {
          params: { q: searchQuery.trim().toUpperCase() },
        });
        const raw = Array.isArray(res.data) ? res.data : res.data?.instruments || [];
        const items: InstrumentResult[] = raw.map((i: any) => {
          const seg = i.exchange_segment || i.segment || "NSE_EQ";
          const isMcx = seg === "MCX_COMM" || seg.includes("MCX");
          const isBse = seg.startsWith("BSE") || seg.includes("BFO");
          const isNfo = seg === "NSE_FNO" || seg.includes("FNO");
          const exch = isMcx ? "MCX" : (isBse ? "BSE" : (isNfo ? "NFO" : (i.exchange || "NSE")));
          return {
            symbol: i.symbol,
            name: i.name || i.symbol,
            exchange: exch,
            segment: seg,
            token: String(i.security_id || i.token || "0"),
            security_id: String(i.security_id || i.token || "0"),
          };
        });
        setSearchResults(items);
      } catch (err) {
        console.error("Instrument search failed", err);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Local filtered watchlist
  const filteredWatchlist = useMemo(() => {
    if (!searchQuery.trim() || searchResults.length > 0) return watchlist;
    const q = searchQuery.toLowerCase().trim();
    return watchlist.filter((item) => item.symbol.toLowerCase().includes(q));
  }, [watchlist, searchQuery, searchResults]);

  const handleAddFromSearch = async (inst: InstrumentResult) => {
    try {
      await onAddToWatchlist(inst);
      toast.success(`Added ${inst.symbol} to watchlist`);
      setSearchQuery("");
      setSearchResults([]);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to add symbol");
    }
  };

  return (
    <div className="space-y-3 pb-24 px-3 pt-2">
      {/* Search Bar */}
      <div className="relative">
        <Search size={15} className="absolute left-3 top-2.5" style={{ color: "var(--muted)" }} />
        <input
          type="text"
          placeholder="Search stocks, indices, futures, options..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full h-9 pl-9 pr-8 rounded-xl text-xs focus:outline-hidden"
          style={{
            background: "var(--surface2)",
            border: "1px solid var(--border)",
            color: "var(--text)",
          }}
        />
        {isSearching && (
          <Loader2 size={14} className="absolute right-3 top-2.5 animate-spin" style={{ color: "var(--green)" }} />
        )}
      </div>

      {/* Search Results Dropdown / Panel */}
      {searchResults.length > 0 && (
        <div
          className="rounded-2xl p-2.5 space-y-1 shadow-xl animate-in fade-in"
          style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
            Matching Instruments ({searchResults.length})
          </div>
          <div className="max-h-60 overflow-y-auto space-y-1">
            {searchResults.map((inst) => {
              const alreadyInList = watchlist.some((w) => w.symbol === inst.symbol);
              return (
                <div
                  key={`${inst.exchange}-${inst.symbol}`}
                  className="flex items-center justify-between p-2 rounded-xl transition-all text-xs"
                  style={{ background: "var(--surface2)" }}
                >
                  <div>
                    <span className="font-bold block" style={{ color: "var(--text)" }}>{inst.symbol}</span>
                    <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
                      {inst.exchange} • {inst.segment || "EQ"}
                    </span>
                  </div>

                  {isAdmin && (
                    <button
                      onClick={() => handleAddFromSearch(inst)}
                      disabled={alreadyInList}
                      className="px-3 py-1.5 rounded-xl text-xs font-bold flex items-center space-x-1 transition-all active:scale-95 shadow-sm"
                      style={{
                        background: alreadyInList ? "var(--surface)" : "var(--green)",
                        color: alreadyInList ? "var(--muted)" : "var(--bg)",
                        border: alreadyInList ? "1px solid var(--border)" : "none",
                      }}
                    >
                      {alreadyInList ? <Check size={12} /> : <Plus size={12} />}
                      <span>{alreadyInList ? "Added" : "Add"}</span>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Watchlist Counter */}
      <div className="flex items-center justify-between px-1 text-xs font-medium" style={{ color: "var(--muted)" }}>
        <span>Tracked Symbols ({watchlist.length})</span>
        <button
          onClick={onRefresh}
          className="text-[11px] font-semibold active:opacity-70"
          style={{ color: "var(--green)" }}
        >
          Refresh Feed
        </button>
      </div>

      {/* Watchlist Items */}
      {filteredWatchlist.length > 0 ? (
        <div className="space-y-2">
          {filteredWatchlist.map((item) => (
            <WatchlistCard
              key={item.id}
              item={item}
              isAdmin={isAdmin}
              onOpenDetail={(i) => setSelectedItem(i)}
              onQuickAddToAlgo={onAddToAlgo}
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
            <ListOrdered size={24} />
          </div>
          <div>
            <h4 className="text-sm font-bold" style={{ color: "var(--text)" }}>Watchlist is Empty</h4>
            <p className="text-xs mt-1 max-w-xs mx-auto" style={{ color: "var(--muted)" }}>
              Search for symbols above to add them to your live monitoring feed.
            </p>
          </div>
        </div>
      )}

      {/* Symbol Detail Bottom Sheet */}
      <SymbolDetailDrawer
        item={selectedItem}
        isOpen={Boolean(selectedItem)}
        isAdmin={isAdmin}
        onClose={() => setSelectedItem(null)}
        onAddToAlgo={onAddToAlgo}
        onRemoveFromWatchlist={onRemoveFromWatchlist}
        onOpenOrder={onOpenOrder}
      />
    </div>
  );
};
