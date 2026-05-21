import type { Candle, LinePoint, BandPoint } from "./types";
import type { MACDPoint } from "./indicators";
import { CoordinateSystem, THEME } from "./types";

// ── Grid & axes ───────────────────────────────────────────────────────────────

export function drawGrid(ctx: CanvasRenderingContext2D, cs: CoordinateSystem) {
  ctx.clearRect(0, 0, cs.width, cs.height);

  // Background
  ctx.fillStyle = THEME.bg;
  ctx.fillRect(0, 0, cs.width, cs.height);

  // Horizontal price grid lines
  const priceSteps = 6;
  ctx.strokeStyle = THEME.grid;
  ctx.lineWidth   = 1;

  for (let i = 0; i <= priceSteps; i++) {
    const price = cs.priceMin + (cs.priceMax - cs.priceMin) * (i / priceSteps);
    const y     = Math.round(cs.priceToY(price)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(cs.chartWidth, y);
    ctx.stroke();
  }

  // Price axis labels (right side)
  ctx.fillStyle  = THEME.text;
  ctx.font       = "11px 'JetBrains Mono', monospace";
  ctx.textAlign  = "left";
  ctx.textBaseline = "middle";

  for (let i = 0; i <= priceSteps; i++) {
    const price = cs.priceMin + (cs.priceMax - cs.priceMin) * (i / priceSteps);
    const y     = cs.priceToY(price);
    ctx.fillText(formatPrice(price), cs.chartWidth + 6, y);
  }

  // Divider line between chart and price axis
  ctx.strokeStyle = THEME.border;
  ctx.lineWidth   = 1;
  ctx.beginPath();
  ctx.moveTo(cs.chartWidth + 0.5, 0);
  ctx.lineTo(cs.chartWidth + 0.5, cs.chartHeight);
  ctx.stroke();

  // Time axis divider
  ctx.beginPath();
  ctx.moveTo(0, cs.chartHeight + 0.5);
  ctx.lineTo(cs.chartWidth, cs.chartHeight + 0.5);
  ctx.stroke();
}

export function drawTimeAxis(
  ctx:     CanvasRenderingContext2D,
  cs:      CoordinateSystem,
  candles: Candle[],
) {
  ctx.fillStyle    = THEME.text;
  ctx.font         = "10px 'JetBrains Mono', monospace";
  ctx.textAlign    = "center";
  ctx.textBaseline = "middle";

  const step = Math.max(1, Math.floor((cs.visibleEnd - cs.visibleStart) / 6));

  for (let i = cs.visibleStart; i <= cs.visibleEnd; i += step) {
    if (i >= candles.length) break;
    const x = cs.indexToX(i);
    const d = new Date(candles[i].time * 1000);
    const label = `${d.getHours().toString().padStart(2,"0")}:${d.getMinutes().toString().padStart(2,"0")}`;
    ctx.fillText(label, x, cs.chartHeight + cs.timeAxisHeight / 2);

    // Tick mark
    ctx.strokeStyle = THEME.border;
    ctx.lineWidth   = 1;
    ctx.beginPath();
    ctx.moveTo(x + 0.5, cs.chartHeight);
    ctx.lineTo(x + 0.5, cs.chartHeight + 4);
    ctx.stroke();
  }
}

// ── Candles ───────────────────────────────────────────────────────────────────

export function drawCandles(
  ctx:     CanvasRenderingContext2D,
  cs:      CoordinateSystem,
  candles: Candle[],
) {
  for (let i = cs.visibleStart; i <= cs.visibleEnd; i++) {
    if (i >= candles.length) break;
    const c     = candles[i];
    const x     = cs.indexToX(i);
    const isBull = c.close >= c.open;
    const color  = isBull ? THEME.bullCandle : THEME.bearCandle;
    const cw     = cs.candleWidth;

    const openY  = cs.priceToY(c.open);
    const closeY = cs.priceToY(c.close);
    const highY  = cs.priceToY(c.high);
    const lowY   = cs.priceToY(c.low);

    const bodyTop    = Math.min(openY, closeY);
    const bodyHeight = Math.max(1, Math.abs(closeY - openY));

    // Wick
    ctx.strokeStyle = color;
    ctx.lineWidth   = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(x) + 0.5, Math.round(highY));
    ctx.lineTo(Math.round(x) + 0.5, Math.round(lowY));
    ctx.stroke();

    // Body
    ctx.fillStyle = isBull ? color : color;
    if (isBull) {
      ctx.fillStyle = color;
    } else {
      ctx.fillStyle = color;
    }
    ctx.fillRect(Math.round(x - cw / 2), Math.round(bodyTop), cw, bodyHeight);

    // Hollow bull candle outline for clarity
    if (isBull && bodyHeight > 2) {
      ctx.strokeStyle = color;
      ctx.lineWidth   = 1;
      ctx.strokeRect(Math.round(x - cw / 2) + 0.5, Math.round(bodyTop) + 0.5, cw - 1, bodyHeight - 1);
    }
  }
}

// ── Volume ────────────────────────────────────────────────────────────────────

export function drawVolume(
  ctx:           CanvasRenderingContext2D,
  cs:            CoordinateSystem,
  candles:       Candle[],
  heightFraction = 0.2,   // fraction of chart height for volume bars
) {
  const maxVol = Math.max(...candles.slice(cs.visibleStart, cs.visibleEnd + 1).map(c => c.volume));
  if (maxVol === 0) return;

  const volHeight = cs.chartHeight * heightFraction;
  const baseY     = cs.chartHeight;

  for (let i = cs.visibleStart; i <= cs.visibleEnd; i++) {
    if (i >= candles.length) break;
    const c      = candles[i];
    const x      = cs.indexToX(i);
    const isBull = c.close >= c.open;
    const barH   = (c.volume / maxVol) * volHeight;

    ctx.fillStyle = isBull ? THEME.volumeBull : THEME.volumeBear;
    ctx.fillRect(Math.round(x - cs.candleWidth / 2), Math.round(baseY - barH), cs.candleWidth, Math.max(1, barH));
  }
}

// ── Line indicator ────────────────────────────────────────────────────────────

export function drawLine(
  ctx:    CanvasRenderingContext2D,
  cs:     CoordinateSystem,
  points: LinePoint[],
  color:  string,
  width = 1.5,
) {
  const visible = points.filter(p => p.index >= cs.visibleStart && p.index <= cs.visibleEnd);
  if (visible.length < 2) return;

  ctx.strokeStyle = color;
  ctx.lineWidth   = width;
  ctx.lineJoin    = "round";
  ctx.beginPath();

  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    const y = cs.priceToY(p.value);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

// ── Bollinger Bands ───────────────────────────────────────────────────────────

export function drawBollingerBands(
  ctx:    CanvasRenderingContext2D,
  cs:     CoordinateSystem,
  bands:  BandPoint[],
) {
  const visible = bands.filter(p => p.index >= cs.visibleStart && p.index <= cs.visibleEnd);
  if (visible.length < 2) return;

  // Fill band area
  ctx.fillStyle = "rgba(88,166,255,0.06)";
  ctx.beginPath();
  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    if (i === 0) ctx.moveTo(x, cs.priceToY(p.upper));
    else ctx.lineTo(x, cs.priceToY(p.upper));
  });
  for (let i = visible.length - 1; i >= 0; i--) {
    const p = visible[i];
    ctx.lineTo(cs.indexToX(p.index), cs.priceToY(p.lower));
  }
  ctx.closePath();
  ctx.fill();

  // Upper band
  ctx.strokeStyle = THEME.bb;
  ctx.lineWidth   = 1;
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    const y = cs.priceToY(p.upper);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Lower band
  ctx.beginPath();
  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    const y = cs.priceToY(p.lower);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.setLineDash([]);

  // Middle (SMA20)
  ctx.strokeStyle = THEME.bb;
  ctx.lineWidth   = 1;
  ctx.beginPath();
  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    const y = cs.priceToY(p.middle);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
}

// ── RSI sub-pane ──────────────────────────────────────────────────────────────

export function drawRSIPane(
  ctx:    CanvasRenderingContext2D,
  cs:     CoordinateSystem,
  rsi:    LinePoint[],
  paneY:  number,       // top of RSI pane
  paneH:  number,       // height of RSI pane
) {
  const visible = rsi.filter(p => p.index >= cs.visibleStart && p.index <= cs.visibleEnd);
  if (visible.length < 2) return;

  // Pane background
  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.fillRect(0, paneY, cs.chartWidth, paneH);

  // Pane border
  ctx.strokeStyle = THEME.border;
  ctx.lineWidth   = 1;
  ctx.strokeRect(0, paneY, cs.chartWidth, paneH);

  // RSI label
  ctx.fillStyle  = THEME.text;
  ctx.font       = "10px 'JetBrains Mono', monospace";
  ctx.textAlign  = "left";
  ctx.fillText("RSI(14)", 6, paneY + 14);

  // Overbought / oversold lines
  const yOB = paneY + paneH * (1 - 70 / 100);
  const yOS = paneY + paneH * (1 - 30 / 100);

  ctx.strokeStyle = "rgba(255,68,102,0.3)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(0, yOB); ctx.lineTo(cs.chartWidth, yOB); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(0, yOS); ctx.lineTo(cs.chartWidth, yOS); ctx.stroke();
  ctx.setLineDash([]);

  // OB/OS labels
  ctx.fillStyle = "rgba(255,68,102,0.6)";
  ctx.fillText("70", cs.chartWidth - 24, yOB - 2);
  ctx.fillText("30", cs.chartWidth - 24, yOS - 2);

  // RSI line
  ctx.strokeStyle = THEME.rsi;
  ctx.lineWidth   = 1.5;
  ctx.beginPath();
  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    const y = paneY + paneH * (1 - p.value / 100);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Current RSI value
  if (visible.length > 0) {
    const last = visible[visible.length - 1];
    ctx.fillStyle = THEME.rsi;
    ctx.textAlign = "right";
    ctx.fillText(last.value.toFixed(1), cs.chartWidth - 4, paneY + 14);
  }
}

// ── MACD sub-pane ─────────────────────────────────────────────────────────────

export function drawMACDPane(
  ctx:   CanvasRenderingContext2D,
  cs:    CoordinateSystem,
  macd:  MACDPoint[],
  paneY: number,
  paneH: number,
) {
  const visible = macd.filter(p => p.index >= cs.visibleStart && p.index <= cs.visibleEnd);
  if (visible.length < 2) return;

  ctx.fillStyle = "rgba(0,0,0,0.3)";
  ctx.fillRect(0, paneY, cs.chartWidth, paneH);
  ctx.strokeStyle = THEME.border;
  ctx.lineWidth   = 1;
  ctx.strokeRect(0, paneY, cs.chartWidth, paneH);

  ctx.fillStyle = THEME.text;
  ctx.font      = "10px 'JetBrains Mono', monospace";
  ctx.textAlign = "left";
  ctx.fillText("MACD(12,26,9)", 6, paneY + 14);

  const values  = visible.flatMap(p => [p.macd, p.signal, p.histogram]);
  const maxAbs  = Math.max(0.001, Math.max(...values.map(Math.abs)));
  const midY    = paneY + paneH / 2;
  const scale   = (paneH / 2 - 4) / maxAbs;

  // Zero line
  ctx.strokeStyle = THEME.border;
  ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.moveTo(0, midY); ctx.lineTo(cs.chartWidth, midY); ctx.stroke();
  ctx.setLineDash([]);

  // Histogram bars
  visible.forEach(p => {
    const x = cs.indexToX(p.index);
    const h = p.histogram * scale;
    ctx.fillStyle = p.histogram >= 0 ? "rgba(0,255,136,0.4)" : "rgba(255,68,102,0.4)";
    ctx.fillRect(x - cs.candleWidth / 2, midY - (h > 0 ? h : 0), cs.candleWidth, Math.abs(h) || 1);
  });

  // MACD line
  ctx.strokeStyle = THEME.ma9;
  ctx.lineWidth   = 1.5;
  ctx.beginPath();
  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    const y = midY - p.macd * scale;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Signal line
  ctx.strokeStyle = THEME.ma21;
  ctx.lineWidth   = 1.5;
  ctx.beginPath();
  visible.forEach((p, i) => {
    const x = cs.indexToX(p.index);
    const y = midY - p.signal * scale;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
}

// ── Crosshair ─────────────────────────────────────────────────────────────────

export function drawCrosshair(
  ctx:    CanvasRenderingContext2D,
  cs:     CoordinateSystem,
  mouseX: number,
  mouseY: number,
  candle: Candle | null,
) {
  if (!candle) return;

  ctx.strokeStyle = THEME.crosshair;
  ctx.lineWidth   = 1;
  ctx.setLineDash([4, 4]);

  // Vertical line
  ctx.beginPath();
  ctx.moveTo(mouseX + 0.5, 0);
  ctx.lineTo(mouseX + 0.5, cs.chartHeight);
  ctx.stroke();

  // Horizontal line
  ctx.beginPath();
  ctx.moveTo(0, mouseY + 0.5);
  ctx.lineTo(cs.chartWidth, mouseY + 0.5);
  ctx.stroke();

  ctx.setLineDash([]);

  // Price label on right axis
  const price = cs.yToPrice(mouseY);
  const labelH = 18;
  const labelY = mouseY - labelH / 2;

  ctx.fillStyle = "#00ff88";
  ctx.fillRect(cs.chartWidth, labelY, cs.priceAxisWidth, labelH);
  ctx.fillStyle  = "#0d1117";
  ctx.font       = "11px 'JetBrains Mono', monospace";
  ctx.textAlign  = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(formatPrice(price), cs.chartWidth + 6, mouseY);
}

// ── OHLCV Tooltip ─────────────────────────────────────────────────────────────

export function drawTooltip(
  ctx:    CanvasRenderingContext2D,
  cs:     CoordinateSystem,
  candle: Candle,
  mouseX: number,
) {
  const isBull  = candle.close >= candle.open;
  const change  = ((candle.close - candle.open) / candle.open * 100).toFixed(2);
  const lines   = [
    `O: ${formatPrice(candle.open)}`,
    `H: ${formatPrice(candle.high)}`,
    `L: ${formatPrice(candle.low)}`,
    `C: ${formatPrice(candle.close)}`,
    `V: ${formatVolume(candle.volume)}`,
    `${isBull ? "▲" : "▼"} ${change}%`,
  ];

  const pad  = 8;
  const lh   = 16;
  const tw   = 130;
  const th   = lines.length * lh + pad * 2;
  let tx     = mouseX + 12;
  if (tx + tw > cs.chartWidth) tx = mouseX - tw - 12;
  const ty   = 8;

  ctx.fillStyle   = THEME.tooltip;
  ctx.strokeStyle = THEME.tooltipBorder;
  ctx.lineWidth   = 1;
  ctx.fillRect(tx, ty, tw, th);
  ctx.strokeRect(tx + 0.5, ty + 0.5, tw - 1, th - 1);

  ctx.font      = "11px 'JetBrains Mono', monospace";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";

  lines.forEach((line, i) => {
    const isLast = i === lines.length - 1;
    ctx.fillStyle = isLast
      ? (isBull ? "#00ff88" : "#ff4466")
      : i < 4 ? "#e8f5e9" : "#4a5568";
    ctx.fillText(line, tx + pad, ty + pad + i * lh);
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatPrice(p: number): string {
  if (p >= 10000) return p.toFixed(0);
  if (p >= 1000)  return p.toFixed(1);
  return p.toFixed(2);
}

function formatVolume(v: number): string {
  if (v >= 10_000_000) return `${(v / 10_000_000).toFixed(1)}Cr`;
  if (v >= 100_000)    return `${(v / 100_000).toFixed(1)}L`;
  if (v >= 1_000)      return `${(v / 1_000).toFixed(0)}K`;
  return v.toString();
}
