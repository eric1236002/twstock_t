import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Backtest, type Candle, type EventRow, type Quota, type ScrapeJob, type Summary } from "@/lib/api";
import { Header } from "@/components/Header";
import { LogDrawer } from "@/components/LogDrawer";
import { Sidebar } from "@/components/Sidebar";
import { KlineChart } from "@/components/KlineChart";
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
    setBacktest(null);
    Promise.all([api.kline(selectedCode, 540), api.backtest(selectedCode)])
      .then(([k, b]) => {
        setCandles(k.data);
        setBacktest(b);
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

        <main className="flex min-w-0 flex-1 flex-col bg-slate-950">
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
              <div className="flex items-baseline justify-between border-b border-slate-800 px-5 py-3">
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

              <div className="h-[44%] min-h-[280px] border-b border-slate-800">
                <KlineChart candles={candles} events={eventsForSelected} />
              </div>

              <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-auto p-4 xl:grid-cols-[2fr_1fr]">
                <div className="min-w-0">
                  <h3 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    事件 · 後續報酬 · 籌碼
                  </h3>
                  <EventsTable events={eventsForSelected} />
                </div>
                <div className="min-w-0">
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
