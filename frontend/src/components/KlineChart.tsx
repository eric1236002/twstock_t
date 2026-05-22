import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { Candle, EventDetail } from "@/lib/api";

type Props = {
  candles: Candle[];
  events: EventDetail[];
};

export function KlineChart({ candles, events }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "#0b0f14" },
        textColor: "#cbd5e1",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155", timeVisible: false },
      crosshair: { mode: 1 },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#ef4444",        // 紅漲 (台股慣例)
      downColor: "#22c55e",      // 綠跌
      borderUpColor: "#ef4444",
      borderDownColor: "#22c55e",
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
    });
    const vol = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "#475569",
    });
    vol.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    seriesRef.current = series;
    volRef.current = vol;
    markersRef.current = createSeriesMarkers(series, []);

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volRef.current = null;
      markersRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !volRef.current) return;
    seriesRef.current.setData(
      candles.map((c) => ({
        time: c.date as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );
    volRef.current.setData(
      candles.map((c) => ({
        time: c.date as Time,
        value: c.volume,
        color: c.close >= c.open ? "#7f1d1d" : "#14532d",
      }))
    );

    const markers: SeriesMarker<Time>[] = events
      .filter((e) => e.anchor_date)
      .map((e) => ({
        time: e.anchor_date as Time,
        position: "aboveBar" as const,
        color: e.doc_type.includes("增資") ? "#06b6d4" : "#f59e0b",
        shape: "arrowDown" as const,
        text: e.doc_type.includes("增資") ? "增" : "債",
      }));
    markersRef.current?.setMarkers(markers);
    chartRef.current?.timeScale().fitContent();
  }, [candles, events]);

  return <div ref={containerRef} className="h-full w-full" />;
}
