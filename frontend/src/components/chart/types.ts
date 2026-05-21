// ── Core data types ───────────────────────────────────────────────────────────

export interface Candle {
  time:   number;   // unix timestamp (seconds)
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}

export interface Point {
  x: number;
  y: number;
}

// ── Coordinate system ─────────────────────────────────────────────────────────

export class CoordinateSystem {
  // Viewport dimensions
  width  = 0;
  height = 0;

  // Price axis (right side)
  priceAxisWidth = 70;

  // Time axis (bottom)
  timeAxisHeight = 28;

  // Visible data range
  visibleStart = 0;   // index into candles array
  visibleEnd   = 0;

  // Price range (with padding)
  priceMin = 0;
  priceMax = 0;

  // Candle layout
  candleWidth  = 8;
  candleGap    = 2;

  get chartWidth()  { return this.width  - this.priceAxisWidth; }
  get chartHeight() { return this.height - this.timeAxisHeight; }

  /** Map candle index → pixel x (centre of candle) */
  indexToX(index: number): number {
    const step = this.candleWidth + this.candleGap;
    const offset = index - this.visibleStart;
    return offset * step + this.candleWidth / 2;
  }

  /** Map price → pixel y */
  priceToY(price: number): number {
    const range = this.priceMax - this.priceMin;
    if (range === 0) return this.chartHeight / 2;
    return this.chartHeight - ((price - this.priceMin) / range) * this.chartHeight;
  }

  /** Map pixel x → candle index */
  xToIndex(x: number): number {
    const step = this.candleWidth + this.candleGap;
    return Math.floor(x / step) + this.visibleStart;
  }

  /** Map pixel y → price */
  yToPrice(y: number): number {
    const range = this.priceMax - this.priceMin;
    return this.priceMax - (y / this.chartHeight) * range;
  }

  /** Recalculate price range from visible candles */
  fitPriceRange(candles: Candle[]) {
    const visible = candles.slice(this.visibleStart, this.visibleEnd + 1);
    if (!visible.length) return;

    let min = Infinity;
    let max = -Infinity;
    for (const c of visible) {
      if (c.low  < min) min = c.low;
      if (c.high > max) max = c.high;
    }

    const pad = (max - min) * 0.08;
    this.priceMin = min - pad;
    this.priceMax = max + pad;
  }

  /** How many candles fit in the chart width */
  get visibleCount(): number {
    return Math.floor(this.chartWidth / (this.candleWidth + this.candleGap));
  }
}

// ── Theme ─────────────────────────────────────────────────────────────────────

export const THEME = {
  bg:           "#0d1117",
  grid:         "rgba(255,255,255,0.04)",
  border:       "#30363d",
  text:         "#4a5568",
  textBright:   "#e8f5e9",
  bullCandle:   "#00ff88",
  bearCandle:   "#ff4466",
  bullWick:     "#00ff88",
  bearWick:     "#ff4466",
  volume:       "rgba(88,166,255,0.25)",
  volumeBull:   "rgba(0,255,136,0.25)",
  volumeBear:   "rgba(255,68,102,0.25)",
  crosshair:    "rgba(255,255,255,0.3)",
  tooltip:      "#161b22",
  tooltipBorder:"rgba(0,255,136,0.3)",
  ma9:          "#58a6ff",
  ma21:         "#ffd060",
  ma50:         "#ff6b9d",
  ema9:         "#79c0ff",
  rsi:          "#d2a8ff",
  vwap:         "#f78166",
  bb:           "rgba(88,166,255,0.5)",
} as const;

// ── Indicator result types ────────────────────────────────────────────────────

export interface LinePoint {
  index: number;
  value: number;
}

export interface BandPoint {
  index: number;
  upper: number;
  middle: number;
  lower: number;
}
