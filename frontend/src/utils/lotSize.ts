/**
 * Lot Size Utility for Indian Markets (NSE, BSE, MCX)
 * Resolves standard contract lot sizes for Options, Futures, and Commodities.
 */

export function resolveLotSize(symbol?: string, segment?: string, fallbackLot?: number): number {
  if (fallbackLot && fallbackLot > 0) return fallbackLot;
  const sym = (symbol || "").toUpperCase().trim();
  const seg = (segment || "").toUpperCase().trim();

  // Index derivatives
  if (sym.includes("BANKNIFTY")) return 15;
  if (sym.includes("FINNIFTY")) return 25;
  if (sym.includes("MIDCPNIFTY")) return 50;
  if (sym.includes("NIFTY")) return 25;
  if (sym.includes("SENSEX")) return 20;
  if (sym.includes("BANKEX")) return 15;

  // MCX Commodities
  if (sym.includes("CRUDEOILM")) return 10;
  if (sym.includes("CRUDEOIL") || sym.includes("CRUDE")) return 100;
  if (sym.includes("NATGASMINI") || sym.includes("NATURALGASM")) return 250;
  if (sym.includes("NATURALGAS") || sym.includes("NATGAS")) return 1250;
  if (sym.includes("GOLDM")) return 10;
  if (sym.includes("GOLDPETAL")) return 1;
  if (sym.includes("GOLD")) return 100;
  if (sym.includes("SILVERMIC")) return 1;
  if (sym.includes("SILVERM")) return 5;
  if (sym.includes("SILVER")) return 30;
  if (sym.includes("COPPER")) return 2500;
  if (sym.includes("ZINC") || sym.includes("LEAD") || sym.includes("ALUMINIUM")) return 5000;

  // Stock options known multipliers
  if (sym.includes("RELIANCE")) return 250;
  if (sym.includes("TCS")) return 175;
  if (sym.includes("INFY")) return 400;
  if (sym.includes("HDFCBANK")) return 550;
  if (sym.includes("TATAMOTORS")) return 700;
  if (sym.includes("SBIN")) return 750;
  if (sym.includes("ICICIBANK")) return 700;
  if (sym.includes("BHARTIARTL")) return 475;
  if (sym.includes("ITC")) return 1600;

  // Default for Equity Cash is 1 share
  return 1;
}

export function formatQuantityWithLots(qty: number, lotSize: number): string {
  if (!lotSize || lotSize <= 1) {
    return `${qty} Qty`;
  }
  const lots = Math.max(1, Math.round(qty / lotSize));
  return `${lots}L (${qty})`;
}
