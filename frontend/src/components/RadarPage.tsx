import { useCallback, useEffect, useRef, useState } from "react";
import { api, type RadarResponse, type RadarStatus } from "@/lib/api";

type Props = { onSelectCode: (code: string) => void };

export function RadarPage({ onSelectCode }: Props) {
  const [data, setData] = useState<RadarResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<RadarStatus | null>(null);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .radar()
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  // 重新整理 = 去抓最新資料(背景),完成後重載清單
  const refresh = useCallback(() => {
    if (status?.running) return;
    setError(null);
    api
      .radarRefresh()
      .then((s) => {
        setStatus(s);
        if (pollRef.current) window.clearInterval(pollRef.current);
        pollRef.current = window.setInterval(async () => {
          try {
            const st = await api.radarStatus();
            setStatus(st);
            if (!st.running) {
              if (pollRef.current) window.clearInterval(pollRef.current);
              pollRef.current = null;
              if (st.error) setError(st.error);
              load(); // reload list with freshly-fetched data
            }
          } catch (e) {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            setError(String(e));
          }
        }, 1500);
      })
      .catch((e) => setError(String(e)));
  }, [status?.running, load]);

  useEffect(() => {
    load(); // initial: read current cache only (no fetch)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [load]);

  const refreshing = !!status?.running;

  const cands = data?.candidates ?? [];
  const confirmed = cands.filter((c) => c.confirmed).length;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-baseline justify-between">
          <h1 className="font-mono text-lg font-semibold text-slate-100">CB 策略雷達</h1>
          <button
            onClick={refresh}
            disabled={refreshing || loading}
            className="rounded border border-slate-700 px-3 py-1 font-mono text-xs text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
          >
            {refreshing
              ? `更新中… ${status?.done ?? 0}/${status?.total ?? 0}`
              : "重新整理"}
          </button>
        </div>

        <p className="mt-2 text-sm leading-relaxed text-slate-400">
          篩選條件:在外可轉債的<span className="text-slate-200">發行轉換價 ±5%</span> 內、且該 CB
          <span className="text-slate-200"> 距到期/賣回 &lt; 180 天</span>。
          <span className="text-amber-300">「確認」</span>=
          投信近 5 日淨買超(回測中把月內噴≥20% 機率約翻倍)。
        </p>
        <p className="mt-1 text-xs text-slate-600">
          觀察名單,非買進建議。樣本小、偏近期、轉換價未還原調整,詳見策略報告。
          {data?.as_of && <span className="ml-2">資料日 {data.as_of}</span>}
        </p>

        {error && (
          <div className="mt-4 rounded border border-rose-900 bg-rose-950/40 px-3 py-2 font-mono text-xs text-rose-300">
            {error}
          </div>
        )}

        <div className="mt-4 flex gap-2 font-mono text-xs">
          <span className="rounded bg-slate-800 px-2 py-1 text-slate-300">符合 {cands.length}</span>
          <span className="rounded bg-amber-500/15 px-2 py-1 text-amber-300">投信確認 {confirmed}</span>
        </div>

        {!loading && cands.length === 0 && !error && (
          <div className="mt-8 text-center text-sm text-slate-600">目前沒有符合條件的個股</div>
        )}

        {cands.length > 0 && (
          <table className="mt-4 w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left font-mono text-[11px] uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3">代號 / 名稱</th>
                <th className="px-2 text-right">收盤</th>
                <th className="px-2 text-right">轉換價</th>
                <th className="px-2 text-right">價差</th>
                <th className="px-2 text-right">距到期</th>
                <th className="px-2 text-right">投信5日(張)</th>
                <th className="px-2 text-center">融券↑</th>
                <th className="px-2 text-center">狀態</th>
              </tr>
            </thead>
            <tbody>
              {cands.map((c) => (
                <tr
                  key={c.code}
                  className={
                    "border-b border-slate-900 transition hover:bg-slate-900/60 " +
                    (c.confirmed ? "bg-amber-500/5" : "")
                  }
                >
                  <td className="py-2 pr-3">
                    <button
                      onClick={() => onSelectCode(c.code)}
                      className="text-left transition hover:brightness-125"
                    >
                      <span className="font-mono font-semibold text-slate-100">{c.code}</span>
                      <span className="ml-2 text-slate-300">{c.name}</span>
                      <span className="ml-2 font-mono text-[10px] text-slate-600">{c.cb_name}</span>
                    </button>
                  </td>
                  <td className="px-2 text-right font-mono text-slate-300">{c.close.toFixed(1)}</td>
                  <td className="px-2 text-right font-mono text-slate-400">{c.conv_price.toFixed(1)}</td>
                  <td
                    className={
                      "px-2 text-right font-mono " +
                      (c.conv_pos_pct < 0 ? "text-emerald-400" : "text-slate-400")
                    }
                  >
                    {c.conv_pos_pct > 0 ? "+" : ""}
                    {c.conv_pos_pct}%
                  </td>
                  <td
                    className={
                      "px-2 text-right font-mono " +
                      (c.days_to_deadline <= 30 ? "text-rose-400" : "text-slate-300")
                    }
                  >
                    {c.days_to_deadline}d
                  </td>
                  <td
                    className={
                      "px-2 text-right font-mono " +
                      (c.trust5_zhang == null
                        ? "text-slate-600"
                        : c.trust5_zhang > 0
                        ? "text-emerald-400"
                        : c.trust5_zhang < 0
                        ? "text-rose-400"
                        : "text-slate-500")
                    }
                  >
                    {c.trust5_zhang == null ? "—" : (c.trust5_zhang > 0 ? "+" : "") + c.trust5_zhang}
                  </td>
                  <td className="px-2 text-center text-slate-400">{c.short_up ? "是" : "·"}</td>
                  <td className="px-2 text-center">
                    {c.confirmed ? (
                      <span className="rounded bg-amber-500/20 px-1.5 py-0.5 font-mono text-[10px] font-medium text-amber-300">
                        確認
                      </span>
                    ) : (
                      <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                        觀察
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
