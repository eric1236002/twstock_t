import datetime as dt, os, sqlite3, sys
ROOT = "/Users/eric/Documents/twstock_t"; sys.path.insert(0, ROOT); os.chdir(ROOT)
from web import kline
conn = sqlite3.connect(os.path.join(ROOT, "twstock.db"))
ev = {r[0] for r in conn.execute("SELECT DISTINCT code FROM events")}
kl = {r[0] for r in conn.execute("SELECT DISTINCT code FROM kline")}
conn.close()
codes = sorted(ev - kl)
end = dt.date.today(); start = end - dt.timedelta(days=1460)
print(f"fetching kline for {len(codes)} event stocks missing it", flush=True)
ok = err = 0
for i, code in enumerate(codes, 1):
    try:
        kline.get_kline(code, start=start, end=end); ok += 1
        if i % 25 == 0: print(f"[{i}/{len(codes)}] ok={ok} err={err}", flush=True)
    except Exception as e:
        err += 1; print(f"[{i}/{len(codes)}] {code}: ERR {e}", flush=True)
print(f"DONE ok={ok} err={err}", flush=True)
