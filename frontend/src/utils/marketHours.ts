export interface MarketSessionState {
  isOpen: boolean; // True if any exchange is open for live trading (NSE or MCX)
  isPre: boolean;  // True during NSE pre-market (09:00 - 09:15)
  isPost: boolean; // True during NSE post-market (15:30 - 16:00)
  nseStatus: "PRE-MARKET" | "OPEN" | "POST-MARKET" | "CLOSED";
  mcxStatus: "OPEN" | "CLOSED";
  badgeText: string;
  shortText: string;
  tooltip: string;
  color: string;
  bg: string;
  border: string;
  pulse: boolean;
}

/**
 * Returns real-time market session status for Indian exchanges (NSE, BSE, MCX) in IST.
 *
 * Session hours:
 * - NSE / BSE Equity & F&O:
 *     Pre-Market:   09:00 - 09:15 IST
 *     Regular:      09:15 - 15:30 IST
 *     Post-Market:  15:30 - 16:00 IST
 *     Closed:       16:00 - 09:00 IST
 * - MCX Commodity Derivatives (Gold, Silver, Crude Oil, Natural Gas, Base Metals):
 *     Morning:      09:00 - 17:00 IST
 *     Evening:      17:00 - 23:55 IST (winter trading schedule)
 *     Closed:       23:55 - 09:00 IST
 */
export function getIndianMarketStatus(): MarketSessionState {
  const now = new Date();
  const istDate = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = istDate.getDay(); // 0 = Sun, 6 = Sat
  const mins = istDate.getHours() * 60 + istDate.getMinutes();

  // Weekend
  if (day === 0 || day === 6) {
    return {
      isOpen: false,
      isPre: false,
      isPost: false,
      nseStatus: "CLOSED",
      mcxStatus: "CLOSED",
      badgeText: "MARKET CLOSED (WEEKEND)",
      shortText: "CLOSED (WEEKEND)",
      tooltip: "Indian exchanges closed on weekends. NSE & MCX open Monday at 09:00 IST.",
      color: "var(--red)",
      bg: "rgba(255,59,87,0.1)",
      border: "rgba(255,59,87,0.35)",
      pulse: false,
    };
  }

  // Weekday NSE status
  let nseStatus: "PRE-MARKET" | "OPEN" | "POST-MARKET" | "CLOSED" = "CLOSED";
  if (mins >= 540 && mins < 555) {
    nseStatus = "PRE-MARKET";
  } else if (mins >= 555 && mins <= 930) {
    nseStatus = "OPEN";
  } else if (mins > 930 && mins <= 960) {
    nseStatus = "POST-MARKET";
  } else {
    nseStatus = "CLOSED";
  }

  // Weekday MCX status: 09:00 - 23:55 IST (mins 540 to 1435)
  const mcxOpen = mins >= 540 && mins < 1435;
  const mcxStatus: "OPEN" | "CLOSED" = mcxOpen ? "OPEN" : "CLOSED";

  // State 1: Both NSE and MCX fully open (09:15 to 15:30 IST)
  if (nseStatus === "OPEN" && mcxOpen) {
    return {
      isOpen: true,
      isPre: false,
      isPost: false,
      nseStatus,
      mcxStatus,
      badgeText: "MARKET OPEN",
      shortText: "OPEN",
      tooltip: "NSE Equity & F&O: OPEN (09:15 - 15:30) • MCX Commodity: OPEN (09:00 - 23:55 IST)",
      color: "var(--green)",
      bg: "rgba(0,230,118,0.1)",
      border: "rgba(0,230,118,0.35)",
      pulse: true,
    };
  }

  // State 2: NSE Pre-Market & MCX Open (09:00 to 09:15 IST)
  if (nseStatus === "PRE-MARKET") {
    return {
      isOpen: true,
      isPre: true,
      isPost: false,
      nseStatus,
      mcxStatus,
      badgeText: "NSE PRE • MCX OPEN",
      shortText: "NSE PRE",
      tooltip: "NSE in Pre-Market session (09:00 - 09:15) • MCX Commodity trading is LIVE (09:00 - 23:55 IST)",
      color: "var(--yellow)",
      bg: "rgba(255,183,3,0.1)",
      border: "rgba(255,183,3,0.35)",
      pulse: true,
    };
  }

  // State 3: NSE Post-Market & MCX Open (15:30 to 16:00 IST)
  if (nseStatus === "POST-MARKET") {
    return {
      isOpen: true,
      isPre: false,
      isPost: true,
      nseStatus,
      mcxStatus,
      badgeText: "NSE POST • MCX OPEN",
      shortText: "MCX OPEN",
      tooltip: "NSE Equity in Post-Market closing session (15:30 - 16:00) • MCX Commodity trading is LIVE till 23:55 IST",
      color: "var(--yellow)",
      bg: "rgba(255,183,3,0.1)",
      border: "rgba(255,183,3,0.35)",
      pulse: true,
    };
  }

  // State 4: NSE Closed & MCX Open (16:00 to 23:55 IST)
  if (mcxOpen && nseStatus === "CLOSED") {
    return {
      isOpen: true,
      isPre: false,
      isPost: false,
      nseStatus,
      mcxStatus,
      badgeText: "NSE CLOSED • MCX OPEN (till 23:55)",
      shortText: "MCX OPEN",
      tooltip: "NSE/BSE closed at 15:30 • MCX Commodity trading is actively LIVE until 23:55 IST",
      color: "var(--green)",
      bg: "rgba(0,230,118,0.1)",
      border: "rgba(0,230,118,0.35)",
      pulse: true,
    };
  }

  // State 5: Night closure (23:55 to 09:00 IST)
  return {
    isOpen: false,
    isPre: false,
    isPost: false,
    nseStatus,
    mcxStatus,
    badgeText: "MARKET CLOSED",
    shortText: "CLOSED",
    tooltip: "All exchange sessions closed. Markets reopen Monday-Friday at 09:00 IST.",
    color: "var(--red)",
    bg: "rgba(255,59,87,0.1)",
    border: "rgba(255,59,87,0.35)",
    pulse: false,
  };
}
