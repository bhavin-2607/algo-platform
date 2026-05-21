import { useQuery } from "@tanstack/react-query";
import { api } from "@/utils/api";

export default function TickerBar({ onSelect }: { onSelect?: (sym: string) => void }) {
  const { data: tickers } = useQuery({
    queryKey: ["ticker"],
    queryFn: () => api.get("/market/ticker").then(r => r.data),
    refetchInterval: 5_000,
  });

  if (!tickers?.length) return null;

  // Duplicate for seamless loop
  const items = [...tickers, ...tickers];

  return (
    <div className="ticker-bar">
      <div className="ticker-track">
        {items.map((t: any, i: number) => (
          <div key={i} className="ticker-item" onClick={() => onSelect?.(t.symbol)}>
            <span className="ticker-sym">{t.symbol}</span>
            <span className="ticker-price">₹{t.ltp?.toLocaleString()}</span>
            <span className={t.change_pct >= 0 ? "ticker-up" : "ticker-down"}>
              {t.change_pct >= 0 ? "▲" : "▼"}{Math.abs(t.change_pct).toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
