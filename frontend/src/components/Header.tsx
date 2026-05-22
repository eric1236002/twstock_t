import { Button } from "@/components/ui/button";
import type { Quota } from "@/lib/api";

type Props = {
  quota: Quota | null;
  scraping: boolean;
  onScrape: () => void;
  onToggleLog: () => void;
  hasLog: boolean;
};

export function Header({ quota, scraping, onScrape, onToggleLog, hasLog }: Props) {
  const pct = quota && quota.limit > 0 ? (quota.remaining / quota.limit) * 100 : 100;
  const color =
    pct > 40 ? "text-emerald-400" : pct > 15 ? "text-amber-400" : "text-rose-400";

  return (
    <header className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-5 py-3">
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-sm uppercase tracking-widest text-slate-500">
          twstock_t
        </span>
        <h1 className="text-base font-semibold text-slate-100">
          稿本爬蟲 · K 線回測終端
        </h1>
      </div>

      <div className="flex items-center gap-4">
        {quota && (
          <div className="flex items-center gap-2 font-mono text-xs">
            <span className="text-slate-500">FinMind</span>
            <span className={color}>
              {quota.remaining}/{quota.limit}
            </span>
            <span className="text-slate-600">({quota.tokens} tokens)</span>
          </div>
        )}
        {hasLog && (
          <Button size="sm" variant="outline" onClick={onToggleLog}>
            Log
          </Button>
        )}
        <Button
          size="sm"
          onClick={onScrape}
          disabled={scraping}
          className="bg-amber-500 text-slate-950 hover:bg-amber-400"
        >
          {scraping ? "抓取中…" : "一鍵抓取"}
        </Button>
      </div>
    </header>
  );
}
