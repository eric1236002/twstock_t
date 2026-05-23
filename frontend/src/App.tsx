import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Backtest, type Candle, type CB, type ChipDay, type EventDetail, type EventRow, type Quota, type Summary } from "@/lib/api";

const EMPTY_EVENTS: EventDetail[] = [];
import { Header } from "@/components/Header";
import { Sidebar } from "@/components/Sidebar";
import { Overview } from "@/components/Overview";
import { ScrapePage } from "@/components/ScrapePage";
import { KlineChart, CHIP_LABELS, chartHeightForPanes, type ChipMode } from "@/components/KlineChart";
import { EventsTable } from "@/components/EventsTable";
import { CbPanel } from "@/components/CbPanel";

type Tab = "overview" | "detail" | "scrape";

function loadFavorites(): Set<string> {
  try {
    const s = localStorage.getItem("twstock_favorites");
    return s ? new Set(JSON.parse(s)) : new Set();
  } catch {
    return new Set();
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chip, setChip] = useState<ChipDay[]>([]);
  const [cb, setCb] = useState<CB[]>([]);
  const [chipPanes, setChipPanes] = useState<ChipMode[]>(["foreign", "trust", "short"]);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [loadingKline, setLoadingKline] = useState(false);
  const [loadingRest, setLoadingRest] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(loadFavorites);

  type DetailCache = { candles: Candle[]; backtest: Backtest; chip: ChipDay[]; cb: CB[] };
  const detailCache = useRef<Map<string, DetailCache>>(new Map());

  const toggleFavorite = useCallback((code: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      localStorage.setItem("twstock_favorites", JSON.stringify([...next]));
      return next;
    });
  }, []);

  const refreshAll = useCallback(async () => {
    const [s, e, q] = await Promise.all([
      api.summary(),
      api.events(),
      api.quota().catch(() => null),
    ]);
    setSummary(s);
    setEvents(e);
    setQuota(q);
  }, []);

  useEffect(() => {
    refreshAll().catch(console.error);
  }, [refreshAll]);

  useEffect(() => {
    if (!selectedCode) return;

    const cached = detailCache.current.get(selectedCode);
    if (cached) {
      setCandles(cached.candles);
      setBacktest(cached.backtest);
      setChip(cached.chip);
      setCb(cached.cb);
      setDetailError(null);
      return;
    }

    const code = selectedCode;
    let cancelled = false;
    const partial: Partial<DetailCache> = {};

    const tryCache = () => {
      if (partial.candles && partial.backtest && partial.chip && partial.cb)
        detailCache.current.set(code, partial as DetailCache);
    };

    setDetailError(null);
    setCandles([]);
    setChip([]);
    setCb([]);
    setBacktest(null);
    setLoadingKline(true);
    setLoadingRest(true);

    // Stage 1: kline — shows chart as soon as ready
    api.kline(code, 1460)
      .then((k) => { if (cancelled) return; partial.candles = k.data; setCandles(k.data); tryCache(); })
      .catch((err) => { if (!cancelled) setDetailError(String(err)); })
      .finally(() => { if (!cancelled) setLoadingKline(false); });

    // Stage 2: backtest + chip + cb in parallel
    Promise.all([api.backtest(code), api.chip(code, 1460), api.cb(code)])
      .then(([b, c, cbRes]) => {
        if (cancelled) return;
        partial.backtest = b; partial.chip = c.data; partial.cb = cbRes.data;
        setBacktest(b); setChip(c.data); setCb(cbRes.data);
        tryCache();
      })
      .catch((err) => { if (!cancelled) setDetailError(String(err)); })
      .finally(() => {
        if (!cancelled) { setLoadingRest(false); api.quota().then(setQuota).catch(() => {}); }
      });

    return () => { cancelled = true; };
  }, [selectedCode]);

  const handleOverviewSelect = useCallback((code: string) => {
    setSelectedCode(code);
    setActiveTab("detail");
  }, []);

  const eventsForSelected = backtest?.events ?? EMPTY_EVENTS;
  const selectedName = selectedCode
    ? summary?.codes.find((c) => c.code === selectedCode)?.name ?? null
    : null;

  const tabBtn = (t: Tab, label: string) => (
    <button
      key={t}
      onClick={() => setActiveTab(t)}
      className={
        "border-b-2 px-5 py-2.5 font-mono text-sm transition-colors " +
        (activeTab === t
          ? "border-amber-400 text-amber-300"
          : "border-transparent text-slate-400 hover:text-slate-200")
      }
    >
      {label}
    </button>
  );

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-200">
      <Header quota={quota} />

      <div className="flex shrink-0 border-b border-slate-800 px-4">
        {tabBtn("overview", "總覽")}
        {tabBtn("detail", "詳細分析")}
        {tabBtn("scrape", "爬取")}
      </div>

      {/* Overview tab — keep mounted to preserve state */}
      <div className={activeTab === "overview" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
        <Overview events={events} summary={summary} onSelectCode={handleOverviewSelect} />
      </div>

      {/* Scrape tab */}
      <div className={activeTab === "scrape" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
        <ScrapePage />
      </div>

      {/* Detail tab */}
      <div className={activeTab === "detail" ? "flex min-h-0 flex-1" : "hidden"}>
        <Sidebar
          summary={summary}
          events={events}
          selectedCode={selectedCode}
          favorites={favorites}
          onPickCode={setSelectedCode}
          onToggleFavorite={toggleFavorite}
        />

        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-slate-950">
          {!selectedCode ? (
            <div className="flex flex-1 items-center justify-center text-slate-600">
              <div className="text-center">
                <div className="font-mono text-xs uppercase tracking-widest text-slate-700">
                  no selection
                </div>
                <div className="mt-2 text-sm">← 從左側選一支股票</div>
              </div>
            </div>
          ) : (
            <>
              <div className="flex shrink-0 items-baseline justify-between border-b border-slate-800 px-5 py-3">
                <div className="flex items-baseline gap-3">
                  <h2 className="font-mono text-2xl font-semibold text-slate-100">
                    {selectedCode}
                  </h2>
                  {selectedName && (
                    <span className="text-lg font-medium text-slate-300">{selectedName}</span>
                  )}
                  {backtest && (
                    <span className="font-mono text-xs text-slate-500">
                      {backtest.events.length} events
                    </span>
                  )}
                </div>
                {detailError && (
                  <span className="font-mono text-xs text-rose-400">{detailError}</span>
                )}
              </div>

              <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-800 px-5 py-1.5">
                <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  籌碼面板
                </span>
                {chipPanes.map((m, i) => (
                  <div key={i} className="flex items-center">
                    <select
                      value={m}
                      onChange={(e) => {
                        const next = [...chipPanes];
                        next[i] = e.target.value as ChipMode;
                        setChipPanes(next);
                      }}
                      className="rounded-l border border-slate-700 bg-slate-900 px-2 py-0.5 font-mono text-xs text-amber-300"
                    >
                      {(Object.keys(CHIP_LABELS) as ChipMode[]).map((k) => (
                        <option key={k} value={k}>
                          {CHIP_LABELS[k]}
                        </option>
                      ))}
                    </select>
                    {chipPanes.length > 1 && (
                      <button
                        onClick={() => setChipPanes(chipPanes.filter((_, j) => j !== i))}
                        className="rounded-r border border-l-0 border-slate-700 bg-slate-900 px-1.5 py-0.5 text-xs text-slate-500 hover:text-rose-400"
                        title="移除面板"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
                {chipPanes.length < 4 && (
                  <button
                    onClick={() => setChipPanes([...chipPanes, "dealer"])}
                    className="rounded border border-dashed border-slate-700 px-2 py-0.5 font-mono text-xs text-slate-400 hover:bg-slate-800"
                  >
                    + 面板
                  </button>
                )}
              </div>

              <div
                className="relative shrink-0 border-b border-slate-800"
                style={{ height: chartHeightForPanes(chipPanes.length) }}
              >
                {loadingKline ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-amber-400" />
                    <span className="font-mono text-sm text-slate-500">載入 K 線…</span>
                  </div>
                ) : (
                  <KlineChart
                    candles={candles}
                    events={eventsForSelected}
                    chip={chip}
                    chipPanes={chipPanes}
                    cb={cb}
                  />
                )}
              </div>

              <div className="p-4 pb-0">
                <CbPanel cb={cb} />
              </div>

              <div className="p-4">
                <h3 className="mb-2 font-mono text-sm font-semibold text-white">
                  事件 · 後續報酬 · 籌碼（±5 交易日）
                </h3>
                {loadingRest ? (
                  <div className="flex h-24 items-center justify-center gap-2">
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-700 border-t-amber-400" />
                    <span className="font-mono text-xs text-slate-500">載入事件…</span>
                  </div>
                ) : (
                  <EventsTable events={eventsForSelected} code={selectedCode} />
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
