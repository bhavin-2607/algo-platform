import type { Candle, LinePoint, BandPoint } from "./types";

// ── Simple Moving Average ─────────────────────────────────────────────────────

export function calcSMA(candles: Candle[], period: number): LinePoint[] {
  const result: LinePoint[] = [];
  for (let i = period - 1; i < candles.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) sum += candles[i - j].close;
    result.push({ index: i, value: sum / period });
  }
  return result;
}

// ── Exponential Moving Average ────────────────────────────────────────────────

export function calcEMA(candles: Candle[], period: number): LinePoint[] {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  const result: LinePoint[] = [];

  // Seed with SMA
  let ema = candles.slice(0, period).reduce((s, c) => s + c.close, 0) / period;
  result.push({ index: period - 1, value: ema });

  for (let i = period; i < candles.length; i++) {
    ema = candles[i].close * k + ema * (1 - k);
    result.push({ index: i, value: ema });
  }
  return result;
}

// ── RSI ───────────────────────────────────────────────────────────────────────

export function calcRSI(candles: Candle[], period = 14): LinePoint[] {
  if (candles.length < period + 1) return [];

  const result: LinePoint[] = [];
  let avgGain = 0;
  let avgLoss = 0;

  // Initial averages
  for (let i = 1; i <= period; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    if (diff > 0) avgGain += diff;
    else avgLoss += Math.abs(diff);
  }
  avgGain /= period;
  avgLoss /= period;

  const rs  = avgLoss === 0 ? 100 : avgGain / avgLoss;
  result.push({ index: period, value: 100 - 100 / (1 + rs) });

  for (let i = period + 1; i < candles.length; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? Math.abs(diff) : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    result.push({ index: i, value: rsi });
  }
  return result;
}

// ── VWAP (resets each session — simplified: full dataset) ────────────────────

export function calcVWAP(candles: Candle[]): LinePoint[] {
  const result: LinePoint[] = [];
  let cumTPV = 0;  // cumulative typical price × volume
  let cumVol = 0;

  for (let i = 0; i < candles.length; i++) {
    const tp = (candles[i].high + candles[i].low + candles[i].close) / 3;
    cumTPV += tp * candles[i].volume;
    cumVol += candles[i].volume;
    result.push({ index: i, value: cumVol > 0 ? cumTPV / cumVol : tp });
  }
  return result;
}

// ── Bollinger Bands ───────────────────────────────────────────────────────────

export function calcBollingerBands(
  candles: Candle[],
  period = 20,
  stdDev = 2,
): BandPoint[] {
  const result: BandPoint[] = [];
  for (let i = period - 1; i < candles.length; i++) {
    const slice  = candles.slice(i - period + 1, i + 1).map(c => c.close);
    const mean   = slice.reduce((a, b) => a + b, 0) / period;
    const std    = Math.sqrt(slice.reduce((s, v) => s + (v - mean) ** 2, 0) / period);
    result.push({
      index:  i,
      middle: mean,
      upper:  mean + stdDev * std,
      lower:  mean - stdDev * std,
    });
  }
  return result;
}

// ── MACD ──────────────────────────────────────────────────────────────────────

export interface MACDPoint {
  index:     number;
  macd:      number;
  signal:    number;
  histogram: number;
}

export function calcMACD(
  candles: Candle[],
  fast  = 12,
  slow  = 26,
  signal = 9,
): MACDPoint[] {
  const fastEMA   = calcEMA(candles, fast);
  const slowEMA   = calcEMA(candles, slow);
  if (!fastEMA.length || !slowEMA.length) return [];

  // Align by index
  const slowStart = slowEMA[0].index;
  const macdLine: LinePoint[] = slowEMA.map((s, i) => ({
    index: s.index,
    value: fastEMA.find(f => f.index === s.index)!.value - s.value,
  }));

  // Signal = EMA of MACD line
  const k = 2 / (signal + 1);
  let sig = macdLine.slice(0, signal).reduce((s, p) => s + p.value, 0) / signal;
  const result: MACDPoint[] = [];

  macdLine.forEach((p, i) => {
    if (i < signal - 1) return;
    if (i === signal - 1) {
      result.push({ index: p.index, macd: p.value, signal: sig, histogram: p.value - sig });
      return;
    }
    sig = p.value * k + sig * (1 - k);
    result.push({ index: p.index, macd: p.value, signal: sig, histogram: p.value - sig });
  });
  return result;
}
