import type { EventDetail } from "@/lib/api";

const WINDOWS = ["T+1", "T+5", "T+20", "T+60"];

function pctCls(v: number | null | undefined) {
  if (v === null || v === undefined) return "text-slate-600";
  return v > 0 ? "text-rose-400" : v < 0 ? "text-emerald-400" : "text-slate-400";
}

function fmtPct(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
}

// institutional nets come from FinMind in shares → display in 張 (lots, /1000)
function fmtLot(shares: number | null | undefined) {
  if (shares === null || shares === undefined) return "—";
  const lot = Math.round(shares / 1000);
  return (lot > 0 ? "+" : "") + lot.toLocaleString();
}

// margin balance delta is already in 張
function fmtMargin(lot: number | null | undefined) {
  if (lot === null || lot === undefined) return "—";
  return (lot > 0 ? "+" : "") + lot.toLocaleString();
}

// "2026-04-15 15:06:27" → "04/15 15:06"
function fmtFiled(iso: string) {
  const m = iso.match(/\d{4}-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return m ? `${m[1]}/${m[2]} ${m[3]}:${m[4]}` : iso;
}

// "202605_2313_B011.pdf" → TWSE 稿本搜尋頁 URL
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
      <span className="text-[9px] uppercase tracking-wider text-slate-400">{label}</span>
      <span className={"num text-sm font-medium " + (cls ?? "text-white")}>{value}</span>
    </div>
  );
}

export function EventsTable({ events }: { events: EventDetail[] }) {
  if (events.length === 0) {
    return (
      <div className="rounded border border-slate-800 px-3 py-6 text-center text-xs text-slate-600">
        此股票無事件
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {events.map((e) => {
        const isIssue = e.doc_type.includes("增資");
        const inst = "institutional" in e.chip ? e.chip.institutional : null;
        const margin = "margin" in e.chip ? e.chip.margin : null;
        return (
          <div
            key={e.id}
            className="rounded border border-slate-800 bg-slate-900/30 p-3"
          >
            {/* top row: meta + returns */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              <div className="flex items-center gap-2">
                <span
                  className={
                    "rounded px-1.5 py-0.5 text-[10px] " +
                    (isIssue
                      ? "bg-cyan-500/25 text-cyan-300"
                      : "bg-amber-500/15 text-amber-400")
                  }
                >
                  {isIssue ? "增資" : "公司債"}
                </span>
                {(() => {
                  const effective =
                    e.case_status === "生效" ||
                    (e.case_status == null && !e.doc_type.includes("稿本"));
                  return (
                    <span
                      className={
                        "rounded px-1.5 py-0.5 text-[10px] " +
                        (effective
                          ? "bg-emerald-500/15 text-emerald-400"
                          : "bg-slate-500/20 text-slate-300")
                      }
                    >
                      {effective ? "生效" : "稿本"}
                    </span>
                  );
                })()}
                <span className="num text-sm text-white">{fmtFiled(e.filed_at)}</span>
                {e.file_link && (
                  <a
                    href={twseDocUrl(e.file_link)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded bg-slate-700/50 px-1.5 py-0.5 text-[10px] text-slate-400 hover:bg-slate-700 hover:text-slate-200"
                  >
                    原文
                  </a>
                )}
              </div>

              <Stat label="T+0開" value={e.anchor_open?.toFixed(2) ?? "—"} />
              {WINDOWS.map((w) => {
                const r = e.returns[w];
                return (
                  <Stat
                    key={w}
                    label={w}
                    value={fmtPct(r?.return_pct)}
                    cls={pctCls(r?.return_pct)}
                  />
                );
              })}
            </div>

            {/* bottom row: chip data */}
            <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-slate-800/60 pt-2">
              <span className="text-[9px] uppercase tracking-wider text-slate-400">
                籌碼 ±5日
              </span>
              <Stat label="外資張" value={fmtLot(inst?.foreign_net)} cls={pctCls(inst?.foreign_net)} />
              <Stat label="投信張" value={fmtLot(inst?.trust_net)} cls={pctCls(inst?.trust_net)} />
              <Stat label="自營張" value={fmtLot(inst?.dealer_net)} cls={pctCls(inst?.dealer_net)} />
              <Stat
                label="融資Δ張"
                value={fmtMargin(margin?.margin_delta)}
                cls={pctCls(margin?.margin_delta)}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
