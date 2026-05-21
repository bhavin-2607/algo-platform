import { useEffect, useRef, useCallback, useState } from "react";
import type { Candle } from "./types";
import { CoordinateSystem, THEME } from "./types";
import {
  calcSMA, calcEMA, calcRSI, calcVWAP, calcBollingerBands, calcMACD,
} from "./indicators";
import {
  drawGrid, drawTimeAxis, drawCandles, drawVolume,
  drawLine, drawBollingerBands, drawRSIPane, drawMACDPane,
  drawCrosshair, drawTooltip,
} from "./renderer";

// ── Active indicators config ──────────────────────────────────────────────────

export interface IndicatorConfig {
  ma9?:   boolean;
  ma21?:  boolean;
  ma50?:  boolean;
  ema9?:  boolean;
  vwap?:  boolean;
  bb?:    boolean;
  rsi?:   boolean;
  macd?:  boolean;
  volume?:boolean;
}

interface Props {
  candles:    Candle[];
  indicators: IndicatorConfig;
  height?:    number;
}

// ── Sub-pane heights ──────────────────────────────────────────────────────────
const RSI_H  = 100;
const MACD_H = 110;

export default function Chart({ candles, indicators, height = 480 }: Props) {
  const canvasRef   = useRef<HTMLCanvasElement>(null);
  const overlayRef  = useRef<HTMLCanvasElement>(null);  // crosshair layer
  const containerRef= useRef<HTMLDivElement>(null);
  const csRef       = useRef(new CoordinateSystem());
  const mouseRef    = useRef({ x: -1, y: -1 });

  // Interaction state
  const isDragging  = useRef(false);
  const dragStart   = useRef({ x: 0, visStart: 0 });

  // ── Compute sub-pane layout ─────────────────────────────────────────────────
  const subPaneH = (indicators.rsi ? RSI_H : 0) + (indicators.macd ? MACD_H : 0);

  // ── Full render ─────────────────────────────────────────────────────────────
  const render = useCallback(() => {
    const canvas  = canvasRef.current;
    if (!canvas || !candles.length) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const cs = csRef.current;
    cs.width  = canvas.width;
    cs.height = canvas.height;

    // Reserve bottom of main chart for sub-panes
    const mainChartH = cs.height - cs.timeAxisHeight - subPaneH;

    // Clamp visible range
    cs.visibleEnd   = Math.min(candles.length - 1, cs.visibleEnd);
    cs.visibleStart = Math.max(0, cs.visibleEnd - cs.visibleCount + 1);
    cs.fitPriceRange(candles);

    // Override chartHeight to exclude sub-panes
    const origChartH = cs.chartHeight;
    Object.defineProperty(cs, "chartHeight", { get: () => mainChartH, configurable: true });

    // Main chart
    drawGrid(ctx, cs);
    if (indicators.volume) drawVolume(ctx, cs, candles);
    drawCandles(ctx, cs, candles);

    // Indicators on main chart
    if (indicators.ma9)  drawLine(ctx, cs, calcSMA(candles, 9),   THEME.ma9,  1.5);
    if (indicators.ma21) drawLine(ctx, cs, calcSMA(candles, 21),  THEME.ma21, 1.5);
    if (indicators.ma50) drawLine(ctx, cs, calcSMA(candles, 50),  THEME.ma50, 1.5);
    if (indicators.ema9) drawLine(ctx, cs, calcEMA(candles, 9),   THEME.ema9, 1.5);
    if (indicators.vwap) drawLine(ctx, cs, calcVWAP(candles),     THEME.vwap, 1.5);
    if (indicators.bb)   drawBollingerBands(ctx, cs, calcBollingerBands(candles));

    // Time axis
    drawTimeAxis(ctx, cs, candles);

    // Sub-panes
    let paneY = mainChartH + cs.timeAxisHeight;
    if (indicators.rsi) {
      drawRSIPane(ctx, cs, calcRSI(candles), paneY, RSI_H);
      paneY += RSI_H;
    }
    if (indicators.macd) {
      drawMACDPane(ctx, cs, calcMACD(candles), paneY, MACD_H);
    }

    // Restore
    Object.defineProperty(cs, "chartHeight", {
      get: () => cs.height - cs.timeAxisHeight,
      configurable: true,
    });
  }, [candles, indicators, subPaneH]);

  // ── Crosshair render (separate canvas, fast) ────────────────────────────────
  const renderCrosshair = useCallback(() => {
    const canvas = overlayRef.current;
    if (!canvas || !candles.length) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const { x, y } = mouseRef.current;
    if (x < 0) return;

    const cs    = csRef.current;
    const idx   = cs.xToIndex(x);
    const candle= candles[idx];
    if (!candle) return;

    const mainH = canvas.height - cs.timeAxisHeight - subPaneH;
    Object.defineProperty(cs, "chartHeight", { get: () => mainH, configurable: true });

    drawCrosshair(ctx, cs, x, y, candle);
    if (y < mainH) drawTooltip(ctx, cs, candle, x);

    Object.defineProperty(cs, "chartHeight", {
      get: () => cs.height - cs.timeAxisHeight,
      configurable: true,
    });
  }, [candles, subPaneH]);

  // ── Resize observer ─────────────────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const ro = new ResizeObserver(() => {
      const w = container.clientWidth;
      const h = height + subPaneH;
      [canvasRef, overlayRef].forEach(ref => {
        if (ref.current) { ref.current.width = w; ref.current.height = h; }
      });
      csRef.current.width  = w;
      csRef.current.height = h;
      render();
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [render, height, subPaneH]);

  // ── Re-render when data/indicators change ───────────────────────────────────
  useEffect(() => {
    if (!candles.length) return;
    const cs = csRef.current;
    cs.visibleEnd = candles.length - 1;
    render();
  }, [candles, render]);

  // ── Mouse events ─────────────────────────────────────────────────────────────
  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = overlayRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getPos(e);
    mouseRef.current = { x, y };
    renderCrosshair();

    if (isDragging.current) {
      const dx = dragStart.current.x - x;
      const step = csRef.current.candleWidth + csRef.current.candleGap;
      const shift = Math.round(dx / step);
      const newEnd = Math.min(
        candles.length - 1,
        Math.max(csRef.current.visibleCount - 1, dragStart.current.visStart + shift)
      );
      csRef.current.visibleEnd = newEnd;
      render();
    }
  };

  const onMouseLeave = () => {
    mouseRef.current = { x: -1, y: -1 };
    renderCrosshair();
  };

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x } = getPos(e);
    isDragging.current = true;
    dragStart.current  = { x, visStart: csRef.current.visibleEnd };
  };

  const onMouseUp = () => { isDragging.current = false; };

  const onWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const cs = csRef.current;

    if (e.ctrlKey || e.metaKey) {
      // Zoom: adjust candle width
      const delta = e.deltaY > 0 ? -1 : 1;
      cs.candleWidth = Math.max(2, Math.min(20, cs.candleWidth + delta));
    } else {
      // Pan: scroll through candles
      const step = e.deltaY > 0 ? 3 : -3;
      cs.visibleEnd = Math.min(
        candles.length - 1,
        Math.max(cs.visibleCount - 1, cs.visibleEnd + step)
      );
    }
    render();
    renderCrosshair();
  };

  const canvasH = height + subPaneH;

  return (
    <div ref={containerRef} style={{ position:"relative", width:"100%", height:canvasH }}>
      {/* Base layer: chart */}
      <canvas ref={canvasRef}
        style={{ position:"absolute", top:0, left:0, display:"block" }} />
      {/* Overlay layer: crosshair + tooltip */}
      <canvas ref={overlayRef}
        style={{ position:"absolute", top:0, left:0, cursor:"crosshair" }}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
        onWheel={onWheel}
      />
    </div>
  );
}
