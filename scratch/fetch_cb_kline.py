import datetime as dt, os, sqlite3, sys
ROOT = "/Users/eric/Documents/twstock_t"
sys.path.insert(0, ROOT); os.chdir(ROOT)
from web import kline

conn = sqlite3.connect(os.path.join(ROOT, "twstock.db"))
codes = [r[0] for r in conn.execute(
    "SELECT DISTINCT stock_code FROM cb WHERE listing_status='2' AND conv_price>0 "
    "AND stock_code != '' ORDER BY stock_code").fetchall()]
conn.close()

end = dt.date.today(); start = end - dt.timedelta(days=1460)
print(f"fetching {len(codes)} CB stocks  {start}..{end}", flush=True)
ok = skip = err = 0
for i, code in enumerate(codes, 1):
    try:
        rows = kline.get_kline(code, start=start, end=end)
        ok += 1
        if i % 20 == 0 or len(rows) == 0:
            print(f"[{i}/{len(codes)}] {code}: {len(rows)} rows  (ok={ok} err={err})", flush=True)
    except Exception as e:
        err += 1
        print(f"[{i}/{len(codes)}] {code}: ERR {type(e).__name__}: {e}", flush=True)
print(f"DONE ok={ok} err={err}", flush=True)
