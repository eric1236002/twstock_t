import { useMemo, useState } from "react";
import type { EventRow, Summary } from "@/lib/api";

type Props = {
  summary: Summary | null;
  events: EventRow[];
  year: string;
  month: string;
  docType: string;
  selectedCode: string | null;
  onYear: (v: string) => void;
  onMonth: (v: string) => void;
  onDocType: (v: string) => void;
  onPickCode: (code: string) => void;
};

export function Sidebar({
  summary,
  events,
  year,
  month,
  docType,
  selectedCode,
  onYear,
  onMonth,
  onDocType,
  onPickCode,
}: Props) {
  const [search, setSearch] = useState("");

  const nameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of summary?.codes ?? []) if (c.name) m.set(c.code, c.name);
    return m;
  }, [summary]);

  // Aggregate filtered events into per-code rows
  const codeRows = useMemo(() => {
    const map = new Map<string, { code: string; n: number; types: Set<string>; last: string }>();
    for (const e of events) {
      const r = map.get(e.code) ?? {
        code: e.code,
        n: 0,
        types: new Set<string>(),
        last: e.filed_at,
      };
      r.n += 1;
      r.types.add(e.doc_type);
      if (e.filed_at > r.last) r.last = e.filed_at;
      map.set(e.code, r);
    }
    return Array.from(map.values()).sort((a, b) => (a.last < b.last ? 1 : -1));
  }, [events]);

  const filteredRows = useMemo(() => {
    if (!search.trim()) return codeRows;
    const q = search.trim().toLowerCase();
    return codeRows.filter(
      (r) =>
        r.code.includes(q) ||
        (nameMap.get(r.code) ?? "").toLowerCase().includes(q),
    );
  }, [codeRows, search, nameMap]);

  return (
    <aside className="flex w-64 flex-col border-r border-slate-800 bg-slate-950">
      <div className="space-y-3 border-b border-slate-800 p-4">
        <div>
          <input
            type="text"
            placeholder="搜尋代號 / 股名"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-amber-500/50"
          />
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-slate-500">
            年
          </label>
          <select
            value={year}
            onChange={(e) => onYear(e.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200"
          >
            <option value="">全部</option>
            {summary?.years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-slate-500">
            月份
          </label>
          <select
            value={month}
            onChange={(e) => onMonth(e.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200"
          >
            <option value="">全部</option>
            {summary?.months.map((m) => (
              <option key={m} value={m}>
                {m} 月
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-slate-500">
            類型
          </label>
          <select
            value={docType}
            onChange={(e) => onDocType(e.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200"
          >
            <option value="">全部</option>
            {summary?.doc_types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <ul className="divide-y divide-slate-800/60">
          {filteredRows.map((r) => {
            const active = r.code === selectedCode;
            const hasBond = Array.from(r.types).some((t) => t.includes("公司債"));
            const hasIssue = Array.from(r.types).some((t) => t.includes("增資"));
            return (
              <li key={r.code}>
                <button
                  onClick={() => onPickCode(r.code)}
                  className={
                    "flex w-full items-center justify-between px-4 py-2 text-left font-mono text-sm transition " +
                    (active
                      ? "bg-amber-500/10 text-amber-300"
                      : "text-slate-300 hover:bg-slate-900")
                  }
                >
                  <span className="flex min-w-0 items-baseline gap-1.5">
                    <span>{r.code}</span>
                    {nameMap.get(r.code) && (
                      <span className="truncate text-xs font-bold text-white">
                        {nameMap.get(r.code)}
                      </span>
                    )}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    {hasBond && (
                      <span className="rounded bg-amber-500/15 px-1.5 text-[10px] text-amber-400">
                        債
                      </span>
                    )}
                    {hasIssue && (
                      <span className="rounded bg-cyan-500/25 px-1.5 text-[10px] text-cyan-300">
                        增
                      </span>
                    )}
                    <span className="ml-1 text-[10px] text-slate-500">×{r.n}</span>
                  </span>
                </button>
              </li>
            );
          })}
          {filteredRows.length === 0 && (
            <li className="px-4 py-6 text-center text-xs text-slate-600">
              {search ? "無符合結果" : "無資料"}
            </li>
          )}
        </ul>
      </div>
    </aside>
  );
}
