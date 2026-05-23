import { useMemo, useState } from "react";
import type { EventRow, Summary } from "@/lib/api";

type Props = {
  events: EventRow[];
  summary: Summary | null;
  onSelectCode: (code: string) => void;
};

type StockRow = {
  code: string;
  market: string | null;
  name: string | null;
  has_bond: boolean;
  has_issue: boolean;
  event_count: number;
  last_event: string;
};

function StockCard({ stock, onClick }: { stock: StockRow; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col gap-1.5 rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-left transition hover:brightness-125 active:scale-95"
    >
      <span className="font-mono text-base font-semibold text-slate-100">{stock.code}</span>
      <div className="truncate text-sm font-medium text-white">{stock.name ?? ""}</div>
      <div className="flex items-center gap-1">
        {stock.has_bond && (
          <span className="rounded bg-amber-500/15 px-1 py-px text-[9px] font-medium text-amber-400">債</span>
        )}
        {stock.has_issue && (
          <span className="rounded bg-cyan-500/25 px-1 py-px text-[9px] font-medium text-cyan-300">增</span>
        )}
        {stock.market === "otc" && (
          <span className="rounded bg-slate-700/60 px-1 py-px text-[9px] text-slate-500">櫃</span>
        )}
        <span className="ml-auto font-mono text-[9px] text-slate-600">×{stock.event_count}</span>
      </div>
    </button>
  );
}

export function Overview({ events, summary, onSelectCode }: Props) {
  const currentMonth = String(new Date().getMonth() + 1).padStart(2, "0");
  const currentYear = String(new Date().getFullYear());
  const [year, setYear] = useState(currentYear);
  const [month, setMonth] = useState(currentMonth);

  const nameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of summary?.codes ?? []) if (c.name) m.set(c.code, c.name);
    return m;
  }, [summary]);

  const years = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) s.add(e.filed_at.substring(0, 4));
    return [...s].sort().reverse();
  }, [events]);

  const months = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) if (e.source_month) s.add(e.source_month);
    return [...s].sort();
  }, [events]);

  const stocks = useMemo((): StockRow[] => {
    const map = new Map<string, StockRow>();
    for (const e of events) {
      if (year && !e.filed_at.startsWith(year)) continue;
      if (month && e.source_month !== month) continue;
      const r = map.get(e.code) ?? {
        code: e.code,
        market: e.market,
        name: nameMap.get(e.code) ?? null,
        has_bond: false,
        has_issue: false,
        event_count: 0,
        last_event: e.filed_at,
      };
      r.event_count += 1;
      if (e.filed_at > r.last_event) r.last_event = e.filed_at;
      if (e.doc_type.includes("公司債")) r.has_bond = true;
      if (e.doc_type.includes("增資")) r.has_issue = true;
      map.set(e.code, r);
    }
    return Array.from(map.values()).sort((a, b) => (a.last_event < b.last_event ? 1 : -1));
  }, [events, year, month, nameMap]);

  const cbCount = stocks.filter((s) => s.has_bond).length;
  const issueCount = stocks.filter((s) => s.has_issue).length;

  const selectClass =
    "rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-amber-500/50";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-slate-800 px-5 py-3">
        <div className="flex gap-6">
          {events.length > 0 ? (
            <>
              <div className="flex flex-col">
                <span className="font-mono text-[9px] uppercase tracking-widest text-slate-500">CB 股</span>
                <span className="font-mono text-sm font-semibold text-slate-200">{cbCount}</span>
              </div>
              <div className="flex flex-col">
                <span className="font-mono text-[9px] uppercase tracking-widest text-slate-500">增資股</span>
                <span className="font-mono text-sm font-semibold text-slate-200">{issueCount}</span>
              </div>
              <div className="flex flex-col">
                <span className="font-mono text-[9px] uppercase tracking-widest text-slate-500">合計</span>
                <span className="font-mono text-sm font-semibold text-slate-200">{stocks.length}</span>
              </div>
            </>
          ) : (
            <span className="font-mono text-xs text-slate-600">載入中…</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <select value={year} onChange={(e) => setYear(e.target.value)} className={selectClass}>
            <option value="">全部年份</option>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={month} onChange={(e) => setMonth(e.target.value)} className={selectClass}>
            <option value="">全部月份</option>
            {months.map((m) => <option key={m} value={m}>{m} 月</option>)}
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {events.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-amber-400" />
            <span className="font-mono text-sm text-slate-500">載入總覽…</span>
          </div>
        ) : stocks.length === 0 ? (
          <div className="flex h-32 items-center justify-center font-mono text-xs text-slate-600">無資料</div>
        ) : (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7 2xl:grid-cols-9">
            {stocks.map((s) => (
              <StockCard key={s.code} stock={s} onClick={() => onSelectCode(s.code)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
