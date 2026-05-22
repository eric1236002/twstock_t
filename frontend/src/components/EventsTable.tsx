import type { EventDetail } from "@/lib/api";

const WINDOWS = ["T+1", "T+5", "T+20", "T+60"];

function pctCls(v: number | undefined) {
  if (v === undefined) return "text-slate-600";
  return v > 0 ? "text-rose-400" : v < 0 ? "text-emerald-400" : "text-slate-400";
}

function fmt(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString();
}

function fmtK(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  const v = n / 1000;
  return (v >= 0 ? "+" : "") + v.toFixed(0) + "K";
}

export function EventsTable({ events }: { events: EventDetail[] }) {
  return (
    <div className="overflow-auto rounded border border-slate-800">
      <table className="w-full font-mono text-xs">
        <thead className="bg-slate-900/60 text-[10px] uppercase tracking-widest text-slate-500">
          <tr>
            <th className="px-3 py-2 text-left">公告時間</th>
            <th className="px-3 py-2 text-left">類型</th>
            <th className="px-3 py-2 text-right">T+0 開盤</th>
            {WINDOWS.map((w) => (
              <th key={w} className="px-3 py-2 text-right">
                {w}
              </th>
            ))}
            <th className="px-3 py-2 text-right">外資</th>
            <th className="px-3 py-2 text-right">投信</th>
            <th className="px-3 py-2 text-right">自營</th>
            <th className="px-3 py-2 text-right">融資Δ</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {events.map((e) => {
            const isIssue = e.doc_type.includes("增資");
            const inst =
              "institutional" in e.chip ? e.chip.institutional : null;
            const margin = "margin" in e.chip ? e.chip.margin : null;
            return (
              <tr key={e.id} className="text-slate-300">
                <td className="px-3 py-2 text-slate-400">{e.filed_at}</td>
                <td className="px-3 py-2">
                  <span
                    className={
                      "rounded px-1.5 py-0.5 text-[10px] " +
                      (isIssue
                        ? "bg-cyan-500/15 text-cyan-400"
                        : "bg-amber-500/15 text-amber-400")
                    }
                  >
                    {isIssue ? "增資" : "公司債"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-slate-300">
                  {e.anchor_open?.toFixed(2) ?? "—"}
                </td>
                {WINDOWS.map((w) => {
                  const r = e.returns[w];
                  return (
                    <td key={w} className={"px-3 py-2 text-right " + pctCls(r?.return_pct)}>
                      {r ? (r.return_pct > 0 ? "+" : "") + r.return_pct.toFixed(2) + "%" : "—"}
                    </td>
                  );
                })}
                <td className={"px-3 py-2 text-right " + pctCls(inst?.foreign_net)}>
                  {fmt(inst?.foreign_net)}
                </td>
                <td className={"px-3 py-2 text-right " + pctCls(inst?.trust_net)}>
                  {fmt(inst?.trust_net)}
                </td>
                <td className={"px-3 py-2 text-right " + pctCls(inst?.dealer_net)}>
                  {fmt(inst?.dealer_net)}
                </td>
                <td className={"px-3 py-2 text-right " + pctCls(margin?.margin_delta ?? undefined)}>
                  {fmtK(margin?.margin_delta)}
                </td>
              </tr>
            );
          })}
          {events.length === 0 && (
            <tr>
              <td colSpan={10} className="px-3 py-6 text-center text-slate-600">
                此股票無事件
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
