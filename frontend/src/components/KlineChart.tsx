import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  createTextWatermark,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type ITextWatermarkPluginApi,
  type SeriesMarker,
  type Time,
  TickMarkType,
} from "lightweight-charts";
import type { Candle, CB, ChipDay, EventDetail } from "@/lib/api";

export type ChipMode = "foreign" | "trust" | "dealer" | "margin" | "short";

export const CHIP_LABELS: Record<ChipMode, string> = {
  foreign: "外資",
  trust: "投信",
  dealer: "自營",
  margin: "融資",
  short: "融券",
};

type Props = {
  candles: Candle[];
  events: EventDetail[];
  chip: ChipDay[];
  chipPanes: ChipMode[];
  cb: CB[];
};

const RED = "#ef4444"; // 紅 = 漲 / 買超 (台股慣例)
const GREEN = "#22c55e"; // 綠 = 跌 / 賣超
const INV_LINE = "#e5e7eb"; // 庫存白線
const CANDLE_H = 360; // 主 K 線固定高度
const CHIP_PANE_H = 40; // 每個籌碼子面板固定高度
const AXIS_H = 32; // 時間軸高度
const SEP = 1;
const PRICE_SCALE_W = 72; // fixed axis width so panes don't shift on data change

/** Total chart pixel height: candle stays fixed, each chip pane adds height. */
export function chartHeightForPanes(n: number): number {
  return CANDLE_H + n * (CHIP_PANE_H + SEP) + AXIS_H;
}

/** Build histogram (買超/日變化) + line (庫存/餘額) data for one chip mode. */
function buildChipSeries(chip: ChipDay[], mode: ChipMode) {
  const bars: { time: Time; value: number; color: string }[] = [];
  const line: { time: Time; value: number }[] = [];

  if (mode === "margin" || mode === "short") {
    let prev: number | null = null;
    for (const d of chip) {
      const bal = mode === "margin" ? d.margin_balance : d.short_balance;
      if (bal == null) continue;
      line.push({ time: d.date as Time, value: bal });
      const delta = prev == null ? 0 : bal - prev;
      bars.push({ time: d.date as Time, value: delta, color: delta >= 0 ? RED : GREEN });
      prev = bal;
    }
  } else {
    const pick =
      mode === "foreign"
        ? (d: ChipDay) => d.foreign_net
        : mode === "trust"
        ? (d: ChipDay) => d.trust_net
        : (d: ChipDay) => d.dealer_net;
    let cum = 0;
    for (const d of chip) {
      const net = pick(d);
      bars.push({ time: d.date as Time, value: net, color: net >= 0 ? RED : GREEN });
      cum += net;
      line.push({ time: d.date as Time, value: cum });
    }
  }
  return { bars, line };
}

/** Robust symmetric bound for the histogram so a single outlier day doesn't
 * blow out the scale (95th percentile of |value|; extremes clip at the edge). */
function robustBound(bars: { value: number }[]): number {
  const abs = bars.map((b) => Math.abs(b.value)).filter((v) => v > 0).sort((a, b) => a - b);
  if (!abs.length) return 1;
  const p95 = abs[Math.min(abs.length - 1, Math.floor(abs.length * 0.95))];
  return Math.max(p95, 1);
}

const CB_LINE = "#a78bfa"; // 轉換價虛線（紫）

export function KlineChart({ candles, events, chip, chipPanes, cb }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const chipSeriesRef = useRef<ISeriesApi<"Histogram" | "Line">[]>([]);
  const watermarkRef = useRef<ITextWatermarkPluginApi<Time>[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const cbLinesRef = useRef<IPriceLine[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      localization: { dateFormat: "yyyy/MM/dd" },
      layout: {
        background: { color: "#0b0f14" },
        textColor: "#cbd5e1",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: 14, // 放大全域字級 → 債/增 marker 文字更醒目（marker 無粗體選項）
        panes: { separatorColor: "#1e293b", separatorHoverColor: "#334155" },
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      rightPriceScale: { borderColor: "#334155", minimumWidth: PRICE_SCALE_W },
      timeScale: {
        borderColor: "#334155",
        timeVisible: false,
        tickMarkFormatter: (time: Time, tickMarkType: TickMarkType) => {
          const s = String(time); // "YYYY-MM-DD"
          const [y, m, d] = s.split("-");
          if (tickMarkType === TickMarkType.Year) return y;
          if (tickMarkType === TickMarkType.Month) return `${y}/${Number(m)}月`;
          return `${y}/${Number(m)}/${Number(d)}`;
        },
      },
      crosshair: { mode: 1 },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: RED,
      downColor: GREEN,
      borderUpColor: RED,
      borderDownColor: GREEN,
      wickUpColor: RED,
      wickDownColor: GREEN,
    });
    const vol = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      color: "#475569",
    });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    chartRef.current = chart;
    seriesRef.current = series;
    volRef.current = vol;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volRef.current = null;
      chipSeriesRef.current = [];
      watermarkRef.current = [];
      markersRef.current = null;
      cbLinesRef.current = [];
    };
  }, []);

  // Price + volume — fitContent only when candles change
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
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Markers — separate effect so fitContent isn't re-triggered when events arrive later
  useEffect(() => {
    if (!seriesRef.current) return;
    const sortedCandleDates = candles.map((c) => c.date);
    const firstDateOnOrAfter = (d: string): string | null => {
      let lo = 0, hi = sortedCandleDates.length;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (sortedCandleDates[mid] < d) lo = mid + 1; else hi = mid; }
      return lo < sortedCandleDates.length ? sortedCandleDates[lo] : null;
    };
    const markers: SeriesMarker<Time>[] = events
      .flatMap((e) => {
        if (!e.filed_at) return [];
        const filedDate = e.filed_at.slice(0, 10);
        const markerDate = firstDateOnOrAfter(filedDate);
        if (!markerDate) return [];
        // Skip if nearest candle is >7 days away (event predates kline range)
        const diffDays = (Date.parse(markerDate) - Date.parse(filedDate)) / 86400000;
        if (diffDays > 7) return [];
        const isIssue = e.doc_type.includes("增資");
        const effective =
          e.case_status === "生效" || (e.case_status == null && !e.doc_type.includes("稿本"));
        const cat = isIssue ? "增" : "債";
        return [{
          time: markerDate as Time,
          position: effective ? "belowBar" : "aboveBar",
          color: isIssue ? "#06b6d4" : "#fbf707",
          shape: effective ? "arrowUp" : "arrowDown",
          text: cat + (effective ? "效" : "稿"),
        }];
      });
    markers.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
    markersRef.current?.detach();
    markersRef.current = createSeriesMarkers(seriesRef.current, markers);
  }, [candles, events]);

  // 可轉債轉換價：每檔 CB 一條水平虛線（右軸標籤＝簡稱）。
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const l of cbLinesRef.current) series.removePriceLine(l);
    cbLinesRef.current = [];
    for (const b of cb) {
      if (!b.conv_price || b.conv_price <= 0) continue;
      cbLinesRef.current.push(
        series.createPriceLine({
          price: b.conv_price,
          color: CB_LINE,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: b.name,
        })
      );
    }
  }, [cb]);

  // Chip sub-panes: one pane per entry, each = 買超 histogram + 庫存 line + 內建 pane 標籤.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const w of watermarkRef.current) w.detach();
    watermarkRef.current = [];
    for (const s of chipSeriesRef.current) chart.removeSeries(s);
    chipSeriesRef.current = [];

    chipPanes.forEach((mode, i) => {
      const paneIndex = i + 1;
      const { bars, line } = buildChipSeries(chip, mode);

      // 庫存白線（畫在下層）
      const inv = chart.addSeries(
        LineSeries,
        {
          color: INV_LINE,
          lineWidth: 1,
          priceScaleId: `inv${i}`,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        },
        paneIndex
      );
      inv.setData(line);
      inv.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });

      // 每日買超長條：後畫蓋在線上，穩健比例尺避免單日離群撐爆
      const bound = robustBound(bars);
      const hist = chart.addSeries(
        HistogramSeries,
        {
          priceFormat: { type: "volume" },
          priceLineVisible: false,
          lastValueVisible: false,
          autoscaleInfoProvider: () => ({
            priceRange: { minValue: -bound, maxValue: bound },
          }),
        },
        paneIndex
      );
      hist.setData(bars);
      hist.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });

      chipSeriesRef.current.push(hist, inv);

      const pane = chart.panes()[paneIndex];
      if (pane) {
        // 內建 pane 文字標籤：函式庫負責定位，會跟著面板移動
        const wm = createTextWatermark(pane, {
          horzAlign: "left",
          vertAlign: "top",
          lines: [{ text: CHIP_LABELS[mode], color: "#fbbf24", fontSize: 12, fontStyle: "bold" }],
        });
        watermarkRef.current.push(wm);
      }
    });

    // 用 stretch factor 而非 setHeight：所有籌碼面板等比例 → 保證等高，
    // 主 K 線維持 CANDLE_H:CHIP_PANE_H 的比例（容器高度已隨面板數成長）。
    const panes = chart.panes();
    if (panes[0]) panes[0].setStretchFactor(CANDLE_H / CHIP_PANE_H);
    for (let i = 1; i < panes.length; i++) panes[i].setStretchFactor(1);
  }, [chip, chipPanes]);

  return <div ref={containerRef} className="h-full w-full" />;
}
