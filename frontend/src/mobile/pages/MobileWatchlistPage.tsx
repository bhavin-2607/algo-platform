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
}

interface MobileWatchlistPageProps {
  watchlist: WatchlistRowData[];
  isAdmin: boolean;
  onRefresh: () => Promise<void>;
  onAddToAlgo: (item: WatchlistRowData) => Promise<void>;
  onAddToWatchlist: (instrument: InstrumentResult) => Promise<void>;
  onRemoveFromWatchlist: (id: string) => Promise<void>;
}

export const MobileWatchlistPage: React.FC<MobileWatchlistPageProps> = ({
  watchlist,
  isAdmin,
  onRefresh,
  onAddToAlgo,
  onAddToWatchlist,
  onRemoveFromWatchlist,
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
        const res = await api.get("/terminal/instruments", {
          params: { q: searchQuery.trim().toUpperCase() },
        });
        setSearchResults(res.data?.instruments || res.data || []);
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
        <Search size={15} className="absolute left-3 top-2.5 text-zinc-500" />
        <input
          type="text"
          placeholder="Search stocks, indices, futures, options..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full h-9 pl-9 pr-8 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-white placeholder-zinc-500 focus:border-emerald-500 focus:outline-hidden"
        />
        {isSearching && (
          <Loader2 size={14} className="absolute right-3 top-2.5 text-emerald-400 animate-spin" />
        )}
      </div>

      {/* Search Results Dropdown / Panel */}
      {searchResults.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-2 space-y-1 shadow-xl animate-in fade-in">
          <div className="px-2 py-1 text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
            Matching Instruments ({searchResults.length})
          </div>
          <div className="max-h-60 overflow-y-auto space-y-1">
            {searchResults.map((inst) => {
              const alreadyInList = watchlist.some((w) => w.symbol === inst.symbol);
              return (
                <div
                  key={`${inst.exchange}-${inst.symbol}`}
                  className="flex items-center justify-between p-2 rounded-lg bg-zinc-950/60 hover:bg-zinc-800/80 transition-all text-xs"
                >
                  <div>
                    <span className="font-bold text-white block">{inst.symbol}</span>
                    <span className="text-[10px] text-zinc-400 font-mono">
                      {inst.exchange} • {inst.segment || "EQ"}
                    </span>
                  </div>

                  {isAdmin && (
                    <button
                      onClick={() => handleAddFromSearch(inst)}
                      disabled={alreadyInList}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center space-x-1 transition-all active:scale-95 ${
                        alreadyInList
                          ? "bg-zinc-800 text-zinc-500 cursor-default"
                          : "bg-emerald-600 hover:bg-emerald-500 text-white"
                      }`}
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
      <div className="flex items-center justify-between px-1 text-xs text-zinc-400 font-medium">
        <span>Tracked Symbols ({watchlist.length})</span>
        <button
          onClick={onRefresh}
          className="text-emerald-400 text-[11px] font-semibold active:opacity-70"
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
        <div className="bg-zinc-900/60 border border-dashed border-zinc-800 rounded-2xl p-8 text-center space-y-4 my-6">
          <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center mx-auto text-zinc-500">
            <ListOrdered size={24} />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white">Watchlist is Empty</h4>
            <p className="text-xs text-zinc-400 mt-1 max-w-xs mx-auto">
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
      />
    </div>
  );
};
