import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Search, X, Plus, BarChart2, Zap } from "lucide-react";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

interface GlobalSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function GlobalSearchModal({ isOpen, onClose }: GlobalSearchModalProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
      setResults([]);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!query || query.trim().length < 2) {
      setResults([]);
      setIsLoading(false);
      return;
    }

    const timer = setTimeout(() => {
      setIsLoading(true);
      api
        .get("/market/instruments", { params: { q: query.trim() } })
        .then((res) => {
          setResults(Array.isArray(res.data) ? res.data.slice(0, 20) : []);
        })
        .catch(() => {
          setResults([]);
        })
        .finally(() => {
          setIsLoading(false);
        });
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  // Handle ESC
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleAddToWatchlist = (item: any) => {
    api
      .post("/terminal/rows", {
        symbol: item.symbol,
        exchange: item.exchange || "NSE",
        segment: item.segment || "NSE_EQ",
        quantity: 1,
      })
      .then(() => {
        toast.success(`Added ${item.symbol} to Watchlist`);
        qc.invalidateQueries({ queryKey: ["terminal-rows"] });
      })
      .catch((err) => {
        toast.error(err.response?.data?.detail || "Failed to add to watchlist");
      });
  };

  const handleAddToAlgo = (item: any) => {
    api
      .post("/terminal/algo-rows", {
        symbol: item.symbol,
        exchange: item.exchange || "NSE",
        segment: item.segment || "NSE_EQ",
        quantity: 1,
        trade_mode: "FULL",
      })
      .then(() => {
        toast.success(`Added ${item.symbol} to Algo Trading Window`);
        qc.invalidateQueries({ queryKey: ["algo-rows"] });
      })
      .catch((err) => {
        toast.error(err.response?.data?.detail || "Failed to add to algo window");
      });
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(4px)",
        zIndex: 99999,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "12vh",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 580,
          maxWidth: "92vw",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          boxShadow: "0 20px 48px rgba(0, 0, 0, 0.6)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Search Input Bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "12px 16px",
            borderBottom: "1px solid var(--border)",
            gap: 10,
            background: "rgba(255, 255, 255, 0.02)",
          }}
        >
          <Search size={16} style={{ color: "var(--green)" }} />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search NSE stock, Index option strike (e.g. NIFTY 25000 CE), or MCX..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              color: "var(--text)",
              fontSize: 13,
              fontFamily: "var(--font)",
            }}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              style={{
                background: "transparent",
                border: "none",
                color: "var(--muted)",
                cursor: "pointer",
                padding: 2,
              }}
            >
              <X size={14} />
            </button>
          )}
          <span
            style={{
              fontSize: 10,
              color: "var(--muted)",
              background: "var(--surface2)",
              border: "1px solid var(--border)",
              borderRadius: 3,
              padding: "2px 6px",
              fontFamily: "monospace",
            }}
          >
            ESC
          </span>
        </div>

        {/* Results List */}
        <div style={{ maxHeight: 380, overflowY: "auto", padding: "6px 0" }}>
          {isLoading && (
            <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--muted)", fontSize: 11 }}>
              Searching Dhan instrument master...
            </div>
          )}

          {!isLoading && query.trim().length >= 2 && results.length === 0 && (
            <div style={{ padding: "28px 16px", textAlign: "center", color: "var(--muted)", fontSize: 11 }}>
              No instruments found for "{query}". Try searching by underlying or strike.
            </div>
          )}

          {!isLoading && query.trim().length < 2 && (
            <div style={{ padding: "28px 16px", textAlign: "center", color: "var(--muted)", fontSize: 11 }}>
              Type at least 2 characters to search stocks, futures, options, and commodities.
            </div>
          )}

          {!isLoading &&
            results.map((item, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "8px 16px",
                  borderBottom: "1px solid rgba(255, 255, 255, 0.03)",
                  transition: "background 0.12s",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as any).style.background = "var(--surface2)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as any).style.background = "transparent";
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                      {item.symbol}
                    </span>
                    <span className="badge badge-gray" style={{ fontSize: 9 }}>
                      {item.exchange || "NSE"}
                    </span>
                    {item.segment && (
                      <span style={{ fontSize: 9, color: "var(--muted)", fontFamily: "monospace" }}>
                        {item.segment}
                      </span>
                    )}
                  </div>
                  {item.name && item.name !== item.symbol && (
                    <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                      {item.name}
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    type="button"
                    onClick={() => handleAddToWatchlist(item)}
                    style={{
                      padding: "4px 8px",
                      fontSize: 10,
                      fontWeight: 700,
                      background: "rgba(0, 230, 118, 0.1)",
                      border: "1px solid rgba(0, 230, 118, 0.3)",
                      color: "var(--green)",
                      borderRadius: 3,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                    title="Add to Watchlist"
                  >
                    <Plus size={11} />
                    <span>WATCHLIST</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleAddToAlgo(item)}
                    style={{
                      padding: "4px 8px",
                      fontSize: 10,
                      fontWeight: 700,
                      background: "rgba(255, 208, 96, 0.1)",
                      border: "1px solid rgba(255, 208, 96, 0.3)",
                      color: "var(--yellow)",
                      borderRadius: 3,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                    title="Add to Algo Trading Window"
                  >
                    <Zap size={11} />
                    <span>ALGO</span>
                  </button>
                </div>
              </div>
            ))}
        </div>

        {/* Footer shortcuts */}
        <div
          style={{
            padding: "8px 16px",
            borderTop: "1px solid var(--border)",
            background: "rgba(0, 0, 0, 0.2)",
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: "var(--muted)",
          }}
        >
          <span>Use Cmd+K / Ctrl+K anywhere to open</span>
          <span>Press ESC to close</span>
        </div>
      </div>
    </div>
  );
}
