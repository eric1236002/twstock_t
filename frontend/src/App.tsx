import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Backtest, type Candle, type ChipDay, type EventRow, type Quota, type ScrapeJob, type Summary } from "@/lib/api";
import { Header } from "@/components/Header";
import { LogDrawer } from "@/components/LogDrawer";
import { Sidebar } from "@/components/Sidebar";
import { KlineChart, CHIP_LABELS, chartHeightForPanes, type ChipMode } from "@/components/KlineChart";
import { EventsTable } from "@/components/EventsTable";
import { StatsTable } from "@/components/StatsTable";

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [month, setMonth] = useState("");
  const [docType, setDocType] = useState("");
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chip, setChip] = useState<ChipDay[]>([]);
  const [chipPanes, setChipPanes] = useState<ChipMode[]>(["foreign", "trust"]);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Scrape job state
  const [jobId, setJobId] = useState<number | null>(null);
  const [job, setJob] = useState<ScrapeJob | null>(null);
  const [logOpen, setLogOpen] = useState(false);

  const refreshAll = useCallback(async () => {
    const [s, e, q] = await Promise.all([
      api.summary(),
      api.events({ month, doc_type: docType }),
      api.quota().catch(() => null),
    ]);
    setSummary(s);
    setEvents(e);
    setQuota(q);
  }, [month, docType]);

  useEffect(() => {
    refreshAll().catch(console.error);
  }, [refreshAll]);

  // Load detail when code selected
  useEffect(() => {
    if (!selectedCode) return;
    setLoadingDetail(true);
    setDetailError(null);
    setCandles([]);
    setChip([]);
    setBacktest(null);
    Promise.all([
      api.kline(selectedCode, 540),
      api.backtest(selectedCode),
      api.chip(selectedCode, 540),
    ])
      .then(([k, b, c]) => {
        setCandles(k.data);
        setBacktest(b);
        setChip(c.data);
      })
      .catch((err) => setDetailError(String(err)))
      .finally(() => {
        setLoadingDetail(false);
        api.quota().then(setQuota).catch(() => {});
      });
  }, [selectedCode]);

  // Scrape job polling
  const pollRef = useRef<number | null>(null);
  useEffect(() => {
    if (!jobId) return;
    const tick = async () => {
      try {
        const j = await api.scrapeJob(jobId);
        setJob(j);
        if (j.status === "running") {
          pollRef.current = window.setTimeout(tick, 1500);
        } else {
          refreshAll().catch(console.error);
        }
      } catch (err) {
        console.error(err);
      }
    };
    tick();
    return () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobId, refreshAll]);

  const startScrape = useCallback(async () => {
    const { job_id } = await api.startScrape();
    setJobId(job_id);
    setLogOpen(true);
  }, []);

  const eventsForSelected = backtest?.events ?? [];
  const stats = backtest?.stats ?? {};
  const scraping = job?.status === "running";

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-200">
      <Header
        quota={quota}
        scraping={scraping}
        onScrape={startScrape}
        onToggleLog={() => setLogOpen(true)}
        hasLog={job !== null}
      />

      <div className="flex min-h-0 flex-1">
        <Sidebar
          summary={summary}
          events={events}
          month={month}
          docType={docType}
          selectedCode={selectedCode}
          onMonth={setMonth}
          onDocType={setDocType}
          onPickCode={setSelectedCode}
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
                  {backtest && (
                    <span className="font-mono text-xs text-slate-500">
                      {backtest.events.length} events
                    </span>
                  )}
                </div>
                {detailError && (
                  <span className="font-mono text-xs text-rose-400">{detailError}</span>
                )}
                {loadingDetail && (
                  <span className="font-mono text-xs text-amber-400">loading…</span>
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
                className="shrink-0 border-b border-slate-800"
                style={{ height: chartHeightForPanes(chipPanes.length) }}
              >
                <KlineChart
                  candles={candles}
                  events={eventsForSelected}
                  chip={chip}
                  chipPanes={chipPanes}
                />
              </div>

              <div className="flex flex-col gap-4 p-4">
                <div className="min-w-0">
                  <h3 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    事件 · 後續報酬 · 籌碼（±5 交易日）
                  </h3>
                  <EventsTable events={eventsForSelected} />
                </div>
                <div className="min-w-0 max-w-xl">
                  <h3 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    聚合統計
                  </h3>
                  <StatsTable stats={stats} />
                </div>
              </div>
            </>
          )}
        </main>
      </div>

      <LogDrawer open={logOpen} onOpenChange={setLogOpen} job={job} />
    </div>
  );
}
