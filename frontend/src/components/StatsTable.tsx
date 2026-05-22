import type { Stats } from "@/lib/api";

const WINDOWS = ["T+1", "T+5", "T+20", "T+60"];

function retCls(v: number) {
  return v > 0 ? "text-rose-400" : v < 0 ? "text-emerald-400" : "text-slate-400";
}
function winCls(v: number) {
  return v >= 50 ? "text-rose-400" : "text-emerald-400";
}

export function StatsTable({ stats }: { stats: Stats }) {
  const rows: { docType: string; window: string; n: number; ret: number; win: number }[] = [];
  for (const [dt, byW] of Object.entries(stats)) {
    for (const w of WINDOWS) {
      const r = byW[w];
      if (r) rows.push({ docType: dt, window: w, n: r.n, ret: r.avg_return_pct, win: r.win_rate_pct });
    }
  }

  return (
    <div className="overflow-auto rounded border border-slate-800">
      <table className="w-full font-mono text-xs">
        <thead className="bg-slate-900/60 text-[10px] uppercase tracking-widest text-slate-500">
          <tr>
            <th className="px-3 py-2 text-left">類型</th>
            <th className="px-3 py-2 text-left">窗口</th>
            <th className="px-3 py-2 text-right">樣本</th>
            <th className="px-3 py-2 text-right">平均報酬</th>
            <th className="px-3 py-2 text-right">勝率</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {rows.map((r, i) => (
            <tr key={i} className="text-slate-300">
              <td className="px-3 py-2">
                <span
                  className={
                    "rounded px-1.5 py-0.5 text-[10px] " +
                    (r.docType.includes("增資")
                      ? "bg-cyan-500/15 text-cyan-400"
                      : "bg-amber-500/15 text-amber-400")
                  }
                >
                  {r.docType.includes("增資") ? "增資" : "公司債"}
                </span>
              </td>
              <td className="px-3 py-2 text-slate-400">{r.window}</td>
              <td className="px-3 py-2 text-right">{r.n}</td>
              <td className={"px-3 py-2 text-right " + retCls(r.ret)}>
                {(r.ret > 0 ? "+" : "") + r.ret.toFixed(2)}%
              </td>
              <td className={"px-3 py-2 text-right " + winCls(r.win)}>
                {r.win.toFixed(1)}%
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="px-3 py-6 text-center text-slate-600">
                樣本不足
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
