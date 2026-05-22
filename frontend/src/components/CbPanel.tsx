import type { CB } from "@/lib/api";

/** 金額單位為千元 → 億（1 億 = 100,000 千元）。 */
function yi(v: number | null): string {
  if (v == null) return "—";
  return (v / 1e5).toFixed(1) + " 億";
}

function pct(v: number | null): string {
  return v == null ? "—" : v.toFixed(2) + "%";
}

export function CbPanel({ cb }: { cb: CB[] }) {
  return (
    <div>
      <h3 className="mb-2 font-mono text-sm font-semibold text-white">
        可轉債 · 轉換價（發行時）
      </h3>
      {cb.length === 0 ? (
        <div className="rounded border border-slate-800 px-3 py-4 text-center text-sm text-slate-400">
          無流通中可轉債
        </div>
      ) : (
        <div className="overflow-auto rounded border border-slate-800">
          <table className="w-full font-mono text-xs">
            <thead className="bg-slate-900/60 text-[10px] uppercase tracking-widest text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left">可轉債</th>
                <th className="px-3 py-2 text-right">轉換價</th>
                <th className="px-3 py-2 text-left">轉換期間</th>
                <th className="px-3 py-2 text-left">到期</th>
                <th className="px-3 py-2 text-right">發行額</th>
                <th className="px-3 py-2 text-right">流通餘額</th>
                <th className="px-3 py-2 text-right">票面利率</th>
                <th className="px-3 py-2 text-left">賣回</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {cb.map((b) => (
                <tr key={b.bond_code} className="text-slate-300">
                  <td className="px-3 py-2">
                    <span className="text-violet-300">{b.name}</span>
                    <span className="ml-1 text-[10px] text-slate-500">{b.bond_code}</span>
                  </td>
                  <td className="px-3 py-2 text-right text-violet-300">
                    {b.conv_price != null ? b.conv_price.toFixed(2) : "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-400">
                    {b.conv_start ?? "?"} ~ {b.conv_end ?? "?"}
                  </td>
                  <td className="px-3 py-2 text-slate-400">{b.maturity_date ?? "—"}</td>
                  <td className="px-3 py-2 text-right">{yi(b.issue_amount)}</td>
                  <td className="px-3 py-2 text-right">{yi(b.outstanding_amount)}</td>
                  <td className="px-3 py-2 text-right">{pct(b.coupon_rate)}</td>
                  <td className="px-3 py-2 text-slate-400">
                    {b.put_date ? `${b.put_date} @ ${b.put_price?.toFixed(2) ?? "?"}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
