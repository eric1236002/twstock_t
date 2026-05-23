import { useEffect, useRef, useState } from "react";
import { api, type ScrapeJob } from "@/lib/api";

const ROC_YEAR = new Date().getFullYear() - 1911;
const THIS_MONTH = new Date().getMonth() + 1;
const YEAR_OPTIONS = Array.from({ length: ROC_YEAR - 109 }, (_, i) => ROC_YEAR - i);

export function ScrapePage() {
  const [year, setYear] = useState(ROC_YEAR);
  const [month, setMonth] = useState<number | "all">(THIS_MONTH);
  const [job, setJob] = useState<ScrapeJob | null>(null);
  const [running, setRunning] = useState(false);
  const logRef = useRef<HTMLPreElement | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [job?.log_total]);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  const poll = (id: number, since: number) => {
    pollRef.current = window.setTimeout(async () => {
      try {
        const j = await api.scrapeJob(id, since);
        setJob(j);
        if (j.status === "running") poll(id, j.log_total);
        else setRunning(false);
      } catch {
        setRunning(false);
      }
    }, 1500);
  };

  const start = async () => {
    if (pollRef.current) clearTimeout(pollRef.current);
    setRunning(true);
    setJob(null);
    try {
      const { job_id } = await api.startScrape({
        year,
        month: month === "all" ? undefined : month,
      });
      poll(job_id, 0);
    } catch (err) {
      setRunning(false);
      console.error(err);
    }
  };

  const statusColor =
    job?.status === "success" ? "text-emerald-400" :
    job?.status === "failed"  ? "text-rose-400" : "text-amber-400";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 p-6">
      <div className="flex items-end gap-4 flex-wrap">
        <div className="flex flex-col gap-1">
          <label className="font-mono text-xs text-slate-500">民國年</label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 font-mono text-sm text-amber-300"
          >
            {YEAR_OPTIONS.map((y) => (
              <option key={y} value={y}>{y} 年</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="font-mono text-xs text-slate-500">月份</label>
          <select
            value={month === "all" ? "all" : month}
            onChange={(e) =>
              setMonth(e.target.value === "all" ? "all" : Number(e.target.value))
            }
            className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 font-mono text-sm text-amber-300"
          >
            <option value="all">全年</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>{m} 月</option>
            ))}
          </select>
        </div>

        <button
          onClick={start}
          disabled={running}
          className="rounded bg-amber-500 px-5 py-1.5 font-mono text-sm font-semibold text-slate-950 hover:bg-amber-400 disabled:opacity-50"
        >
          {running ? "抓取中…" : "開始抓取"}
        </button>

        {job && (
          <div className="flex items-center gap-3 font-mono text-xs text-slate-400">
            <span>Job #{job.id}</span>
            <span className={statusColor}>{job.status}</span>
            {job.rows_inserted > 0 && (
              <span className="text-emerald-400">+{job.rows_inserted} 筆</span>
            )}
          </div>
        )}
      </div>

      <pre
        ref={logRef}
        className="min-h-0 flex-1 overflow-auto rounded border border-slate-800 bg-black p-4 font-mono text-xs leading-relaxed text-slate-300"
      >
        {job?.log.join("\n") || "尚未開始…"}
      </pre>
    </div>
  );
}
