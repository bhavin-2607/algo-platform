import React, { useState, useEffect } from "react";
import { X, TrendingUp, TrendingDown, Layers, ShieldCheck, Check, AlertCircle } from "lucide-react";
import { api } from "@/utils/api";
import { resolveLotSize } from "@/utils/lotSize";
import toast from "react-hot-toast";

interface MobileOrderDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  securityId?: string;
  exchangeSegment?: string;
  exchange?: string;
  ltp?: number;
  initialSide?: "BUY" | "SELL";
  onOrderSuccess?: () => void;
  lotSize?: number;
}

export const MobileOrderDrawer: React.FC<MobileOrderDrawerProps> = ({
  isOpen,
  onClose,
  symbol,
  securityId,
  exchangeSegment,
  exchange,
  ltp = 0,
  initialSide = "BUY",
  onOrderSuccess,
  lotSize: propLotSize,
}) => {
  const [side, setSide] = useState<"BUY" | "SELL">(initialSide);
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">("MARKET");
  const [productType, setProductType] = useState<"INTRADAY" | "MARGIN">("INTRADAY");
  const [limitPrice, setLimitPrice] = useState<string>(ltp > 0 ? ltp.toFixed(2) : "");
  const [lots, setLots] = useState<number>(1);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const [lotSize, setLotSize] = useState<number>(() => resolveLotSize(symbol, exchangeSegment, propLotSize));
  const isDerivative = (exchangeSegment || "").includes("FNO") || (exchangeSegment || "").includes("MCX") || (exchangeSegment || "").includes("BFO") || lotSize > 1;

  useEffect(() => {
    if (propLotSize && propLotSize > 0) {
      setLotSize(propLotSize);
      return;
    }
    const fallback = resolveLotSize(symbol, exchangeSegment);
    setLotSize(fallback);
    if (symbol || securityId) {
      api.get("/terminal/lot-size", { params: { symbol, security_id: securityId } })
        .then((res) => {
          const remoteLot = Number(res.data?.lot_size || 0);
          if (remoteLot > 0) {
            setLotSize(remoteLot);
          }
        })
        .catch(() => {});
    }
  }, [symbol, securityId, exchangeSegment, propLotSize]);

  useEffect(() => {
    setSide(initialSide);
    if (ltp > 0) {
      setLimitPrice(ltp.toFixed(2));
    }
    setLots(1);
    if (isDerivative) {
      setProductType("MARGIN");
    } else {
      setProductType("INTRADAY");
    }
  }, [symbol, initialSide, ltp, isDerivative]);

  if (!isOpen) return null;

  const totalQuantity = lots * lotSize;
  const activePrice = orderType === "LIMIT" ? (parseFloat(limitPrice) || ltp) : ltp;
  const estimatedTotal = (totalQuantity * activePrice).toLocaleString(undefined, { maximumFractionDigits: 1 });

  const handleIncrement = (delta: number) => {
    setLots((prev) => Math.max(1, prev + delta));
  };

  const handleSubmit = async () => {
    if (totalQuantity <= 0) {
      toast.error("Quantity must be greater than zero");
      return;
    }
    if (orderType === "LIMIT" && (!parseFloat(limitPrice) || parseFloat(limitPrice) <= 0)) {
      toast.error("Please enter a valid limit price");
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = {
        symbol: symbol.toUpperCase(),
        security_id: securityId || symbol,
        exchange_segment: exchangeSegment || (exchange === "MCX" ? "MCX_COMM" : "NSE_EQ"),
        transaction_type: side,
        quantity: totalQuantity,
        order_type: orderType,
        product_type: productType,
        price: orderType === "LIMIT" ? parseFloat(limitPrice) : 0.0,
      };

      const res = await api.post("/terminal/order", payload);
      const brokerOrderId = res.data?.order_id || res.data?.broker_order_id || "OK";
      toast.success(`${side} order placed (${totalQuantity}x ${symbol}) - ID: ${brokerOrderId}`);
      if (onOrderSuccess) onOrderSuccess();
      onClose();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : (detail?.error_message || JSON.stringify(detail) || "Order rejected");
      toast.error(`Order failed: ${msg}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mobile-drawer-overlay">
      <div
        className="w-full max-w-lg mobile-drawer-content p-5 space-y-4 animate-in slide-in-from-bottom"
        style={{ background: "var(--surface)", borderTop: "1px solid var(--border)" }}
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between pb-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="min-w-0 flex-1">
            <div className="flex items-center space-x-2">
              <span className="text-base font-extrabold tracking-tight truncate" style={{ color: "var(--text)" }}>
                {symbol}
              </span>
              <span
                className="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium shrink-0"
                style={{ background: "var(--surface2)", color: "var(--muted)", border: "1px solid var(--border)" }}
              >
                {(exchangeSegment?.includes("MCX") || exchange === "MCX") ? "MCX" : (exchange || "NSE")}
              </span>
            </div>
            <div className="text-xs font-mono mt-0.5" style={{ color: "var(--muted)" }}>
              LTP: <strong style={{ color: "var(--text)" }}>{ltp.toFixed(2)}</strong>
              {lotSize > 1 && <span> | Lot: {lotSize}</span>}
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full transition-all active:scale-95 bg-transparent shrink-0"
            style={{ background: "var(--surface2)", color: "var(--muted)" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Side Selector (BUY / SELL) */}
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setSide("BUY")}
            className="h-11 rounded-xl font-extrabold text-sm flex items-center justify-center space-x-1.5 transition-all active:scale-98 shadow-sm"
            style={{
              background: side === "BUY" ? "var(--green)" : "var(--surface2)",
              color: side === "BUY" ? "var(--bg)" : "var(--muted)",
              border: side === "BUY" ? "none" : "1px solid var(--border)",
            }}
          >
            <TrendingUp size={16} />
            <span>BUY</span>
          </button>
          <button
            type="button"
            onClick={() => setSide("SELL")}
            className="h-11 rounded-xl font-extrabold text-sm flex items-center justify-center space-x-1.5 transition-all active:scale-98 shadow-sm"
            style={{
              background: side === "SELL" ? "var(--red)" : "var(--surface2)",
              color: side === "SELL" ? "#ffffff" : "var(--muted)",
              border: side === "SELL" ? "none" : "1px solid var(--border)",
            }}
          >
            <TrendingDown size={16} />
            <span>SELL</span>
          </button>
        </div>

        {/* Product Type (INTRADAY / MARGIN) */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-semibold tracking-wider uppercase block" style={{ color: "var(--muted)" }}>
            Product
          </label>
          <div className="grid grid-cols-2 gap-2 text-xs font-semibold">
            {[
              { id: "INTRADAY", label: "Intraday (MIS)" },
              { id: "MARGIN", label: isDerivative ? "Margin (Normal)" : "Delivery (CNC)" },
            ].map((p) => (
              <button
                type="button"
                key={p.id}
                onClick={() => setProductType(p.id as any)}
                className="h-9 rounded-xl transition-all flex items-center justify-center active:scale-95"
                style={{
                  background: productType === p.id ? "var(--surface2)" : "transparent",
                  color: productType === p.id ? "var(--ba-cyan, var(--blue))" : "var(--muted)",
                  border: productType === p.id ? "1px solid var(--ba-cyan, var(--blue))" : "1px solid var(--border)",
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Order Type (MARKET / LIMIT) */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-semibold tracking-wider uppercase block" style={{ color: "var(--muted)" }}>
            Order Type
          </label>
          <div className="grid grid-cols-2 gap-2 text-xs font-semibold">
            {[
              { id: "MARKET", label: "Market" },
              { id: "LIMIT", label: "Limit" },
            ].map((o) => (
              <button
                type="button"
                key={o.id}
                onClick={() => setOrderType(o.id as any)}
                className="h-9 rounded-xl transition-all flex items-center justify-center active:scale-95"
                style={{
                  background: orderType === o.id ? "var(--surface2)" : "transparent",
                  color: orderType === o.id ? "var(--ba-cyan, var(--blue))" : "var(--muted)",
                  border: orderType === o.id ? "1px solid var(--ba-cyan, var(--blue))" : "1px solid var(--border)",
                }}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {/* Limit Price Input if LIMIT */}
        {orderType === "LIMIT" && (
          <div className="space-y-1.5 animate-in fade-in">
            <label className="text-[11px] font-semibold tracking-wider uppercase block" style={{ color: "var(--muted)" }}>
              Limit Price
            </label>
            <input
              type="number"
              step="0.05"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              className="w-full h-10 px-3 rounded-xl font-mono text-sm focus:outline-hidden"
              style={{
                background: "var(--surface2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            />
          </div>
        )}

        {/* Quantity / Lots Configuration */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-[11px] font-semibold" style={{ color: "var(--muted)" }}>
            <span>{lotSize > 1 ? "NUMBER OF LOTS" : "QUANTITY"}</span>
            <span className="font-mono">
              Total Qty: <strong style={{ color: "var(--text)" }}>{totalQuantity}</strong>
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => handleIncrement(-1)}
              className="w-11 h-11 rounded-xl text-lg font-bold flex items-center justify-center transition-all active:scale-90 bg-transparent shrink-0"
              style={{ background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)" }}
            >
              -
            </button>
            <input
              type="number"
              min="1"
              value={lots}
              onChange={(e) => setLots(Math.max(1, parseInt(e.target.value) || 1))}
              className="flex-1 h-11 rounded-xl text-center font-mono font-bold text-base focus:outline-hidden"
              style={{
                background: "var(--surface2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            />
            <button
              type="button"
              onClick={() => handleIncrement(1)}
              className="w-11 h-11 rounded-xl text-lg font-bold flex items-center justify-center transition-all active:scale-90 bg-transparent shrink-0"
              style={{ background: "var(--surface2)", color: "var(--text)", border: "1px solid var(--border)" }}
            >
              +
            </button>
          </div>

          {/* Quick Lot Multipliers */}
          <div className="flex items-center space-x-1.5 pt-1">
            {[1, 2, 5, 10].map((m) => (
              <button
                type="button"
                key={m}
                onClick={() => setLots(m)}
                className="flex-1 py-1 rounded-lg text-[10px] font-mono font-semibold transition-all active:scale-95"
                style={{
                  background: lots === m ? "var(--green-dim)" : "var(--surface2)",
                  color: lots === m ? "var(--green)" : "var(--muted)",
                  border: lots === m ? "1px solid var(--green)" : "1px solid var(--border)",
                }}
              >
                {m}x
              </button>
            ))}
          </div>
        </div>

        {/* Order Summary Strip */}
        <div
          className="p-3 rounded-xl flex items-center justify-between text-xs font-mono"
          style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
        >
          <span style={{ color: "var(--muted)" }}>Approx Value:</span>
          <span className="font-bold" style={{ color: "var(--text)" }}>
            {estimatedTotal}
          </span>
        </div>

        {/* Execution Submit Button */}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting}
          className="w-full h-12 rounded-xl font-extrabold text-sm flex items-center justify-center space-x-2 transition-all shadow-md active:scale-98"
          style={{
            background: side === "BUY" ? "var(--green)" : "var(--red)",
            color: side === "BUY" ? "var(--bg)" : "#ffffff",
          }}
        >
          {side === "BUY" ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          <span>
            {isSubmitting
              ? "Placing Order..."
              : `${side} ${totalQuantity} ${lotSize > 1 ? `(${lots} LOT${lots > 1 ? "S" : ""})` : "SHARES"}`}
          </span>
        </button>
      </div>
    </div>
  );
};
