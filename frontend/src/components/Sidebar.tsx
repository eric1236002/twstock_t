import { useMemo, useState } from "react";
import type { EventRow, Summary } from "@/lib/api";

type Props = {
  summary: Summary | null;
  events: EventRow[];
  selectedCode: string | null;
  favorites: Set<string>;
  onPickCode: (code: string) => void;
  onToggleFavorite: (code: string) => void;
};

export function Sidebar({
  summary,
  events,
  selectedCode,
  favorites,
  onPickCode,
  onToggleFavorite,
}: Props) {
  const [search, setSearch] = useState("");
  const [year, setYear] = useState("");
  const [month, setMonth] = useState("");
  const [docType, setDocType] = useState("");
  const [view, setView] = useState<"all" | "favorites">("all");

  const nameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of summary?.codes ?? []) if (c.name) m.set(c.code, c.name);
    return m;
  }, [summary]);

  // Derive filter options from all events
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

  const docTypes = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) s.add(e.doc_type);
    return [...s].sort();
  }, [events]);

  // Filter events locally — no API call
  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      if (year && !e.filed_at.startsWith(year)) return false;
      if (month && e.source_month !== month) return false;
      if (docType && e.doc_type !== docType) return false;
      return true;
    });
  }, [events, year, month, docType]);

  // Aggregate into per-code rows
  const codeRows = useMemo(() => {
    const map = new Map<string, { code: string; n: number; types: Set<string>; last: string }>();
    for (const e of filteredEvents) {
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
  }, [filteredEvents]);

  const filteredRows = useMemo(() => {
    let rows = view === "favorites" ? codeRows.filter((r) => favorites.has(r.code)) : codeRows;
    if (!search.trim()) return rows;
    const q = search.trim().toLowerCase();
    return rows.filter(
      (r) =>
        r.code.includes(q) ||
        (nameMap.get(r.code) ?? "").toLowerCase().includes(q),
    );
  }, [codeRows, search, nameMap, view, favorites]);

  const sel = "w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200";

  return (
    <aside className="flex w-64 flex-col border-r border-slate-800 bg-slate-950">
      <div className="space-y-3 border-b border-slate-800 p-4">
        <input
          type="text"
          placeholder="搜尋代號 / 股名"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-amber-500/50"
        />
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-slate-500">年</label>
          <select value={year} onChange={(e) => setYear(e.target.value)} className={`mt-1 ${sel}`}>
            <option value="">全部</option>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-slate-500">月份</label>
          <select value={month} onChange={(e) => setMonth(e.target.value)} className={`mt-1 ${sel}`}>
            <option value="">全部</option>
            {months.map((m) => <option key={m} value={m}>{m} 月</option>)}
          </select>
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-slate-500">類型</label>
          <select value={docType} onChange={(e) => setDocType(e.target.value)} className={`mt-1 ${sel}`}>
            <option value="">全部</option>
            {docTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {/* View toggle */}
      <div className="flex shrink-0 border-b border-slate-800">
        <button
          onClick={() => setView("all")}
          className={
            "flex-1 py-2 font-mono text-xs transition-colors " +
            (view === "all"
              ? "border-b-2 border-amber-400 text-amber-300"
              : "text-slate-500 hover:text-slate-300")
          }
        >
          全部
        </button>
        <button
          onClick={() => setView("favorites")}
          className={
            "flex-1 py-2 font-mono text-xs transition-colors " +
            (view === "favorites"
              ? "border-b-2 border-amber-400 text-amber-300"
              : "text-slate-500 hover:text-slate-300")
          }
        >
          ★ 我的最愛{favorites.size > 0 ? ` (${favorites.size})` : ""}
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        <ul className="divide-y divide-slate-800/60">
          {filteredRows.map((r) => {
            const active = r.code === selectedCode;
            const starred = favorites.has(r.code);
            const hasBond = Array.from(r.types).some((t) => t.includes("公司債"));
            const hasIssue = Array.from(r.types).some((t) => t.includes("增資"));
            return (
              <li key={r.code} className="group flex items-stretch">
                <button
                  onClick={() => onPickCode(r.code)}
                  className={
                    "flex min-w-0 flex-1 items-center justify-between px-4 py-2 text-left font-mono text-sm transition " +
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
                      <span className="rounded bg-amber-500/15 px-1.5 text-[10px] text-amber-400">債</span>
                    )}
                    {hasIssue && (
                      <span className="rounded bg-cyan-500/25 px-1.5 text-[10px] text-cyan-300">增</span>
                    )}
                    <span className="ml-1 text-[10px] text-slate-500">×{r.n}</span>
                  </span>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onToggleFavorite(r.code); }}
                  className={
                    "shrink-0 px-2 text-base transition-colors " +
                    (starred
                      ? "text-amber-400"
                      : "text-slate-700 opacity-0 group-hover:opacity-100 hover:text-amber-400")
                  }
                  title={starred ? "取消收藏" : "加入最愛"}
                >
                  {starred ? "★" : "☆"}
                </button>
              </li>
            );
          })}
          {filteredRows.length === 0 && (
            <li className="px-4 py-6 text-center text-xs text-slate-600">
              {view === "favorites" ? "尚無收藏" : search ? "無符合結果" : "無資料"}
            </li>
          )}
        </ul>
      </div>
    </aside>
  );
}
