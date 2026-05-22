import { useEffect, useState } from "react";
import { api, type OverviewResponse, type OverviewStock } from "@/lib/api";

type Props = {
  onSelectCode: (code: string) => void;
};

function priceColors(pct: number | null): { card: string; pct: string } {
  if (pct === null) return { card: "border-slate-700 bg-slate-900/60", pct: "text-slate-500" };
  if (pct >= 7)  return { card: "border-emerald-400/60 bg-emerald-900/30", pct: "text-emerald-300" };
  if (pct >= 3)  return { card: "border-emerald-500/40 bg-emerald-900/20", pct: "text-emerald-400" };
  if (pct >= 0)  return { card: "border-emerald-800/30 bg-slate-900/80",   pct: "text-emerald-500" };
  if (pct >= -3) return { card: "border-rose-800/30 bg-slate-900/80",      pct: "text-rose-500"    };
  if (pct >= -7) return { card: "border-rose-500/40 bg-rose-900/20",       pct: "text-rose-400"    };
  return           { card: "border-rose-400/60 bg-rose-900/30",            pct: "text-rose-300"    };
}

function StockCard({ stock, onClick }: { stock: OverviewStock; onClick: () => void }) {
  const { card, pct: pctColor } = priceColors(stock.price_change_pct);
  const pct = stock.price_change_pct;
  const pctStr = pct === null ? "—" : (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%";

  return (
    <button
      onClick={onClick}
      className={`flex flex-col gap-1.5 rounded-lg border p-3 text-left transition hover:brightness-125 active:scale-95 ${card}`}
    >
      <div className="flex items-baseline justify-between gap-1">
        <span className="font-mono text-base font-semibold text-slate-100">{stock.code}</span>
        <span className={`font-mono text-sm font-bold tabular-nums ${pctColor}`}>{pctStr}</span>
      </div>
      <div className="truncate text-sm font-medium text-white">
        {stock.name ?? ""}
      </div>
      <div className="flex items-center gap-1">
        {stock.has_bond && (
          <span className="rounded bg-amber-500/15 px-1 py-px text-[9px] font-medium text-amber-400">
            債
          </span>
        )}
        {stock.has_issue && (
          <span className="rounded bg-cyan-500/25 px-1 py-px text-[9px] font-medium text-cyan-300">
            增
          </span>
        )}
        {stock.market === "otc" && (
          <span className="rounded bg-slate-700/60 px-1 py-px text-[9px] text-slate-500">
            櫃
          </span>
        )}
        <span className="ml-auto font-mono text-[9px] text-slate-600">×{stock.event_count}</span>
      </div>
    </button>
  );
}

function StatPill({ label, value, colored }: { label: string; value: string | number; colored?: number | null }) {
  const color =
    colored === undefined || colored === null
      ? "text-slate-200"
      : colored >= 0 ? "text-emerald-400" : "text-rose-400";
  return (
    <div className="flex flex-col">
      <span className="font-mono text-[9px] uppercase tracking-widest text-slate-500">{label}</span>
      <span className={`font-mono text-sm font-semibold tabular-nums ${color}`}>{value}</span>
    </div>
  );
}

export function Overview({ onSelectCode }: Props) {
  const currentMonth = String(new Date().getMonth() + 1).padStart(2, "0");
  const currentYear = String(new Date().getFullYear());
  const [year, setYear] = useState(currentYear);
  const [month, setMonth] = useState(currentMonth);
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .overview({ year: year || undefined, month: month || undefined })
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [year, month]);

  const selectClass =
    "rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-amber-500/50";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Top bar */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-slate-800 px-5 py-3">
        <div className="flex gap-6">
          {data ? (
            <>
              <StatPill label="CB 股" value={data.summary.cb_count} />
              <StatPill label="增資股" value={data.summary.issue_count} />
              <StatPill label="合計" value={data.summary.total} />
              {data.summary.avg_price_change !== null && (
                <StatPill
                  label="平均漲幅 (20日)"
                  value={(data.summary.avg_price_change >= 0 ? "+" : "") + data.summary.avg_price_change.toFixed(1) + "%"}
                  colored={data.summary.avg_price_change}
                />
              )}
            </>
          ) : (
            <span className="font-mono text-xs text-slate-600">載入中…</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <select value={year} onChange={(e) => setYear(e.target.value)} className={selectClass}>
            <option value="">全部年份</option>
            {data?.years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <select value={month} onChange={(e) => setMonth(e.target.value)} className={selectClass}>
            <option value="">全部月份</option>
            {data?.months.map((m) => (
              <option key={m} value={m}>{m} 月</option>
            ))}
          </select>
        </div>
      </div>

      {/* Card grid */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="flex h-32 items-center justify-center font-mono text-xs text-slate-600">
            載入中…
          </div>
        ) : !data || data.stocks.length === 0 ? (
          <div className="flex h-32 items-center justify-center font-mono text-xs text-slate-600">
            無資料
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7 2xl:grid-cols-9">
            {data.stocks.map((s) => (
              <StockCard key={s.code} stock={s} onClick={() => onSelectCode(s.code)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
