import { useEffect, useState } from "react";
import { api, type EventDetail, type NewsItem } from "@/lib/api";

const WINDOWS = ["T+1", "T+5", "T+20", "T+60"];

function pctCls(v: number | null | undefined) {
  if (v === null || v === undefined) return "text-slate-600";
  return v > 0 ? "text-rose-400" : v < 0 ? "text-emerald-400" : "text-slate-400";
}

function fmtPct(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
}

function fmtLot(shares: number | null | undefined) {
  if (shares === null || shares === undefined) return "—";
  const lot = Math.round(shares / 1000);
  return (lot > 0 ? "+" : "") + lot.toLocaleString();
}

function fmtMargin(lot: number | null | undefined) {
  if (lot === null || lot === undefined) return "—";
  return (lot > 0 ? "+" : "") + lot.toLocaleString();
}

function fmtFiled(iso: string) {
  const m = iso.match(/\d{4}-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return m ? `${m[1]}/${m[2]} ${m[3]}:${m[4]}` : iso;
}

function fmtNewsTime(dt: string) {
  const m = dt.match(/\d{4}-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return m ? `${m[1]}/${m[2]} ${m[3]}:${m[4]}` : dt;
}

function twseDocUrl(fileLink: string): string {
  const parts = fileLink.replace(/\.pdf$/i, "").split("_");
  if (parts.length < 2) return "https://doc.twse.com.tw/";
  const yyyymm = parts[0];
  const code = parts[1];
  const calYear = parseInt(yyyymm.slice(0, 4), 10);
  const month = yyyymm.slice(4, 6);
  const rocYear = calYear - 1911;
  return (
    `https://doc.twse.com.tw/server-java/t57sb01` +
    `?id=&key=&step=1&co_id=${code}&year=${rocYear}&seamon=${parseInt(month, 10)}&mtype=B&dtype=`
  );
}

function Stat({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs uppercase tracking-wider text-slate-400">{label}</span>
      <span className={"num text-base font-medium " + (cls ?? "text-white")}>{value}</span>
    </div>
  );
}

function NewsPanel({ code, center }: { code: string; center: string }) {
  const [items, setItems] = useState<NewsItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setItems(null);
    setError(null);
    api.news(code, center)
      .then((r) => { if (!cancelled) setItems(r.data); })
      .catch((e) => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [code, center]);

  if (loading) return (
    <div className="mt-2 border-t border-slate-800/60 pt-2 font-mono text-xs text-slate-500">
      載入新聞…
    </div>
  );
  if (error) return (
    <div className="mt-2 border-t border-slate-800/60 pt-2 font-mono text-xs text-rose-400">
      {error}
    </div>
  );
  if (!items || items.length === 0) return (
    <div className="mt-2 border-t border-slate-800/60 pt-2 font-mono text-xs text-slate-600">
      前後 5 日無新聞紀錄
    </div>
  );

  return (
    <div className="mt-2 space-y-1 border-t border-slate-800/60 pt-2">
      <span className="font-mono text-[9px] uppercase tracking-wider text-slate-500">
        前後 5 日新聞 ({items.length})
      </span>
      {items.map((n, i) => (
        <div key={i} className="flex items-start gap-2 text-base">
          <span className="num shrink-0 text-slate-500">{fmtNewsTime(n.published_at)}</span>
          <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-sm text-slate-400">
            {n.source ?? "—"}
          </span>
          {n.link ? (
            <a
              href={n.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-200 hover:text-amber-300 hover:underline"
            >
              {n.title ?? n.link}
            </a>
          ) : (
            <span className="text-slate-300">{n.title ?? "—"}</span>
          )}
        </div>
      ))}
    </div>
  );
}

type FilterCat = "all" | "bond" | "issue";
type FilterStatus = "all" | "draft" | "effective";

function FilterBtn({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={
        "rounded px-2.5 py-1 text-sm font-medium transition-colors " +
        (active
          ? "bg-amber-500 text-slate-950"
          : "bg-slate-800 text-slate-400 hover:text-slate-200")
      }
    >
      {children}
    </button>
  );
}

export function EventsTable({ events, code }: { events: EventDetail[]; code: string }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [cat, setCat] = useState<FilterCat>("all");
  const [status, setStatus] = useState<FilterStatus>("all");

  if (events.length === 0) {
    return (
      <div className="rounded border border-slate-800 px-3 py-6 text-center text-xs text-slate-600">
        此股票無事件
      </div>
    );
  }

  const filtered = events.filter((e) => {
    const isIssue = e.doc_type.includes("增資");
    const effective =
      e.case_status === "生效" || (e.case_status == null && !e.doc_type.includes("稿本"));
    if (cat === "bond" && isIssue) return false;
    if (cat === "issue" && !isIssue) return false;
    if (status === "draft" && effective) return false;
    if (status === "effective" && !effective) return false;
    return true;
  });

  return (
    <div className="space-y-3">
      {/* filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">類別</span>
        <FilterBtn active={cat === "all"} onClick={() => setCat("all")}>全部</FilterBtn>
        <FilterBtn active={cat === "bond"} onClick={() => setCat("bond")}>公司債</FilterBtn>
        <FilterBtn active={cat === "issue"} onClick={() => setCat("issue")}>增資</FilterBtn>
        <span className="ml-3 text-xs text-slate-500">狀態</span>
        <FilterBtn active={status === "all"} onClick={() => setStatus("all")}>全部</FilterBtn>
        <FilterBtn active={status === "draft"} onClick={() => setStatus("draft")}>稿本</FilterBtn>
        <FilterBtn active={status === "effective"} onClick={() => setStatus("effective")}>生效</FilterBtn>
        <span className="ml-2 text-xs text-slate-600">{filtered.length} / {events.length}</span>
      </div>

      {filtered.length === 0 && (
        <div className="rounded border border-slate-800 px-3 py-6 text-center text-xs text-slate-600">
          無符合條件的事件
        </div>
      )}

      {filtered.map((e) => {
        const isIssue = e.doc_type.includes("增資");
        const effective =
          e.case_status === "生效" || (e.case_status == null && !e.doc_type.includes("稿本"));
        const inst = "institutional" in e.chip ? e.chip.institutional : null;
        const margin = "margin" in e.chip ? e.chip.margin : null;
        const expanded = expandedId === e.id;
        const center = e.filed_at.slice(0, 10);
        return (
          <div
            key={e.id}
            className={
              "rounded border bg-slate-900/30 p-3 transition-colors " +
              (expanded ? "border-amber-500/30" : "border-slate-800")
            }
          >
            {/* top row */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              <div className="flex items-center gap-2">
                <span
                  className={
                    "rounded px-1.5 py-0.5 text-xs " +
                    (isIssue ? "bg-cyan-500/25 text-cyan-300" : "bg-amber-500/15 text-amber-400")
                  }
                >
                  {isIssue ? "增資" : "公司債"}
                </span>
                <span
                  className={
                    "rounded px-1.5 py-0.5 text-xs " +
                    (effective
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-slate-500/20 text-slate-300")
                  }
                >
                  {effective ? "生效" : "稿本"}
                </span>
                <span className="num text-base text-white">{fmtFiled(e.filed_at)}</span>
                {e.file_link && (
                  <a
                    href={twseDocUrl(e.file_link)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded border border-slate-600 px-2 py-0.5 text-sm font-medium text-slate-300 hover:border-amber-500 hover:text-amber-300"
                  >
                    原文 ↗
                  </a>
                )}
              </div>

              <Stat label="T+0開" value={e.anchor_open?.toFixed(2) ?? "—"} />
              {WINDOWS.map((w) => {
                const r = e.returns[w];
                return (
                  <Stat key={w} label={w} value={fmtPct(r?.return_pct)} cls={pctCls(r?.return_pct)} />
                );
              })}

              <button
                onClick={() => setExpandedId(expanded ? null : e.id)}
                className={
                  "ml-auto rounded border px-2.5 py-0.5 text-sm font-medium transition-colors " +
                  (expanded
                    ? "border-amber-500/50 text-amber-400"
                    : "border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-300")
                }
              >
                {expanded ? "▲ 新聞" : "▼ 新聞"}
              </button>
            </div>

            {/* chip row */}
            <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-slate-800/60 pt-2">
              <span className="text-xs uppercase tracking-wider text-slate-400">籌碼 ±5日</span>
              <Stat label="外資張" value={fmtLot(inst?.foreign_net)} cls={pctCls(inst?.foreign_net)} />
              <Stat label="投信張" value={fmtLot(inst?.trust_net)} cls={pctCls(inst?.trust_net)} />
              <Stat label="自營張" value={fmtLot(inst?.dealer_net)} cls={pctCls(inst?.dealer_net)} />
              <Stat label="融資Δ張" value={fmtMargin(margin?.margin_delta)} cls={pctCls(margin?.margin_delta)} />
            </div>

            {expanded && <NewsPanel code={code} center={center} />}
          </div>
        );
      })}
    </div>
  );
}
