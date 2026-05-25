import datetime as dt, os, sqlite3, sys
ROOT = "/Users/eric/Documents/twstock_t"; sys.path.insert(0, ROOT); os.chdir(ROOT)
from web import chip
conn = sqlite3.connect(os.path.join(ROOT, "twstock.db"))
cb = {r[0] for r in conn.execute("SELECT DISTINCT stock_code FROM cb WHERE listing_status='2' AND conv_price>0")}
inst = {r[0] for r in conn.execute("SELECT DISTINCT code FROM institutional")}
mg = {r[0] for r in conn.execute("SELECT DISTINCT code FROM margin")}
conn.close()
codes = sorted(x for x in cb if x not in inst or x not in mg)
end = dt.date.today(); start = end - dt.timedelta(days=1460)
print(f"fetching chip for {len(codes)} CB stocks", flush=True)
ok = err = 0
for i, code in enumerate(codes, 1):
    try:
        chip.ensure_institutional(code, start, end); chip.ensure_margin(code, start, end); ok += 1
        if i % 20 == 0: print(f"[{i}/{len(codes)}] ok={ok} err={err}", flush=True)
    except Exception as e:
        err += 1; print(f"[{i}/{len(codes)}] {code}: ERR {e}", flush=True)
print(f"DONE ok={ok} err={err}", flush=True)
