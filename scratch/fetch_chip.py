import datetime as dt, os, sqlite3, sys
ROOT = "/Users/eric/Documents/twstock_t"
sys.path.insert(0, ROOT); os.chdir(ROOT)
from web import chip

conn = sqlite3.connect(os.path.join(ROOT, "twstock.db"))
codes = [r[0] for r in conn.execute("SELECT DISTINCT code FROM kline ORDER BY code")]
conn.close()
end = dt.date.today(); start = end - dt.timedelta(days=1460)
print(f"fetching institutional+margin for {len(codes)} stocks {start}..{end}", flush=True)
ok = err = 0
for i, code in enumerate(codes, 1):
    try:
        chip.ensure_institutional(code, start, end)
        chip.ensure_margin(code, start, end)
        ok += 1
        if i % 20 == 0:
            print(f"[{i}/{len(codes)}] {code}  (ok={ok} err={err})", flush=True)
    except Exception as e:
        err += 1
        print(f"[{i}/{len(codes)}] {code}: ERR {type(e).__name__}: {e}", flush=True)
print(f"DONE ok={ok} err={err}", flush=True)
