import React, { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

interface EmergencyPanicModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function EmergencyPanicModal({ isOpen, onClose }: EmergencyPanicModalProps) {
  const [isPending, setIsPending] = useState(false);
  const qc = useQueryClient();

  if (!isOpen) return null;

  const handleExecuteKillSwitch = async () => {
    setIsPending(true);
    try {
      const res = await api.post("/terminal/algo-rows/kill-all");
      toast.success(
        `Kill switch executed: ${res.data.positions_exited || 0} position(s) exited, ${res.data.total_scripts || 0} algo(s) disarmed`
      );
      qc.invalidateQueries({ queryKey: ["algo-rows"] });
      qc.invalidateQueries({ queryKey: ["terminal-rows"] });
      qc.invalidateQueries({ queryKey: ["orderbook"] });
      qc.invalidateQueries({ queryKey: ["dhan-positions"] });
      qc.invalidateQueries({ queryKey: ["algo-trade-history"] });
      onClose();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Failed to execute kill switch");
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.8)",
        backdropFilter: "blur(4px)",
        zIndex: 99999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 440,
          maxWidth: "92vw",
          background: "var(--surface)",
          border: "2px solid var(--red)",
          borderRadius: 6,
          boxShadow: "0 20px 48px rgba(255, 68, 102, 0.25)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            background: "rgba(255, 68, 102, 0.12)",
            borderBottom: "1px solid rgba(255, 68, 102, 0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <AlertTriangle size={18} style={{ color: "var(--red)" }} />
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: 1, color: "var(--red)" }}>
              EMERGENCY KILL SWITCH
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--muted)",
              cursor: "pointer",
              padding: 2,
            }}
          >
            <X size={16} />
          </button>
        </div>

        <div style={{ padding: "20px 16px" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 8 }}>
            Square Off All Positions & Disarm All Algos?
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5, marginBottom: 16 }}>
            This action will immediately:
            <ul style={{ margin: "8px 0 0 16px", padding: 0 }}>
              <li>Disarm automated trading across all scripts (ALGO OFF).</li>
              <li>Exit any open intraday positions at market price.</li>
              <li>Record all completed exits into the Trade History.</li>
            </ul>
          </div>

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              style={{
                padding: "8px 16px",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--text)",
                fontFamily: "var(--font)",
                fontSize: 11,
                fontWeight: 600,
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              CANCEL
            </button>
            <button
              type="button"
              onClick={handleExecuteKillSwitch}
              disabled={isPending}
              style={{
                padding: "8px 16px",
                background: "var(--red)",
                border: "1px solid var(--red)",
                color: "#fff",
                fontFamily: "var(--font)",
                fontSize: 11,
                fontWeight: 800,
                letterSpacing: 0.8,
                borderRadius: 4,
                cursor: isPending ? "not-allowed" : "pointer",
                opacity: isPending ? 0.7 : 1,
              }}
            >
              {isPending ? "EXITING ALL..." : "CONFIRM EXIT ALL POSITIONS"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
