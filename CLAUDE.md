# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Three standalone Python scrapers that pull Taiwanese securities filings and write monthly CSV/XLSX outputs. The scripts are shipped as Windows `.exe` bundles produced by PyInstaller — the `.spec` files in the repo root are the build descriptors, and `dist/` / `build/` are PyInstaller artifacts (gitignored). Source filenames are Traditional Chinese.

## Scripts

The 稿本 scraper now lives **inside the web backend** at `web/scraper.py` and covers **both 上市 (listed) and 上櫃 (OTC)** — they share the same TWSE endpoint, so the only difference is which codes are fed. The standalone scripts below have been archived to `old/` (gitignored) as reference — they are no longer wired into anything.

- **`web/scraper.py`** — the live scraper. `run_scrape(log, roc_year, seamon=None, markets=("listed","otc"))` POSTs each code (from `codes/listed.csv` + `codes/otc.csv`) to `https://doc.twse.com.tw/server-java/t57sb01` with 50 workers + `tenacity` retry through the proxy. `seamon=None` sends `seamon=""` → **the whole year in one request per code** (backfill); an int → that single month (ongoing use). Keeps rows whose 資料細節說明 contains 公司債/增資 (both `(稿本)` drafts and 生效 effective rows) and records 結案類型 / 電子檔案 / 上傳日期. Writes straight into `events` via `db.import_rows` — **no intermediate CSV**.
- **`web/codes.py`** — refreshes the code lists from TWSE ISIN: `strMode=2` (上市: 股票+創新板) → `codes/listed.csv` (~1079), `strMode=4` (上櫃: 股票) → `codes/otc.csv` (~887). Excludes 認購(售)權證 / ETF / ETN / TDR / 特別股 / 受益證券. Run `python -m web.codes` or `POST /api/update-codes`.
- **old/上市稿本.py** / **old/上櫃稿本.py** — the original standalone listed / OTC versions `web/scraper.py` was ported from. Both used the same endpoint. Archived reference.
- **old/增資.py** — MOPS capital-increase scraper (`https://mops.twse.com.tw/mops/web/t05st02`), writes `YYYYMMDD{type}結果.xlsx` via openpyxl. **Encoded in Big5** — string literals/comments look like mojibake as UTF-8; preserve the Big5 bytes if editing. Not integrated into the web app.

## Common commands

```bash
# The scraper runs inside the web app — trigger it via POST /api/scrape (the
# "一鍵抓取" button) or directly:
#   python3 -c "from web.scraper import run_listed_scrape; run_listed_scrape(print)"
# (reads .env for proxy, ./上市代碼/CODE.csv for codes, writes ./MM月data.csv)

# Quick proxy / endpoint sanity check (single code, no concurrency)
python scratch/test_request.py
python scratch/test_proxy.py
```

The old PyInstaller `.spec` build descriptors and the Windows `.exe` workflow have been removed (the app is now web-based). If you ever need to rebuild an exe, regenerate a spec with `pyi-makespec`.

There is no `requirements.txt`. The runtime deps used across the scripts are: `httpx`, `requests`, `beautifulsoup4`, `tenacity`, `colorlog`, `python-dotenv`, `urllib3`, `openpyxl`.

## Required configuration

`.env` (gitignored) must define the residential proxy used by `上市稿本.py`:

```
PROXY_USERNAME=...
PROXY_PASSWORD=...
PROXY_HOST=...
PROXY_PORT=...
```

The proxy URL is assembled as `http://{user}:{pass}@{host}:{port}` and passed to `httpx.Client(proxy=..., verify=False)`. TLS verification is intentionally disabled because the upstream endpoint misbehaves through this proxy — keep `verify=False` and the `urllib3.disable_warnings(...)` call unless you have a verified replacement.

## Inputs and outputs

- Input codes: `codes/listed.csv` (上市) + `codes/otc.csv` (上櫃) — one 4-digit code per line, no header, ASCII filenames, checked into git. Regenerate with `python -m web.codes`.
- Output: scraped rows go **straight into the `events` table** (no CSV files anymore).
- The doc endpoint takes `year` = ROC year (`西元 - 1911`) and `seamon`: an int = that month, **empty string `""` = the whole year in one request**. Scraped table columns: `[0]證券代號 [3]結案類型 [5]資料細節說明 [7]電子檔案 [9]上傳日期`.

## Web app (event browser + K-line backtest)

There is a FastAPI app under `web/` that browses the scraper events, triggers the scraper from the UI, and overlays event markers on K-line charts with T+N return stats. Scraped events go straight into SQLite (`twstock.db`); price + chip data come from FinMind.

```bash
# Run the API + serve the bundled React frontend
python3 -m uvicorn web.app:app --host 127.0.0.1 --port 8765

# Frontend dev (Vite on 5173 with /api proxied to 8765)
cd frontend && pnpm dev

# Rebuild the single-file bundle that FastAPI serves at /
cd frontend && bash <path-to>/skills/web-artifacts-builder/scripts/bundle-artifact.sh
cp frontend/bundle.html web/static/bundle.html
```

### Architecture

- `web/db.py` — SQLite schema + helpers. `events` columns: `code, market('listed'|'otc'), doc_type(=資料細節說明), case_status(結案類型), file_link(電子檔案), filed_at(上傳日期), source_month`, `UNIQUE(code, file_link)`. `import_rows()` inserts scraped rows (ROC→ISO, dedup); `rebuild_events()` DROP+CREATEs events (used when backfilling after a schema change). Tables: `events, kline, institutional, margin, stock_names, cb, scrape_jobs`.
- `web/codes.py` — refreshes `codes/listed.csv` + `codes/otc.csv` from TWSE ISIN (see Scripts). `load_codes(markets)` returns `[(code, market), ...]` for the scraper.
- `web/finmind.py` — FinMind REST client. Reads `FINMIND_TOKENS` (comma-separated) from `.env`; picks the least-used non-exhausted token each request; on `402`/`401` marks token exhausted until next top of hour. `get_data(dataset, **params)` is the only entry point. `quota_remaining()` aggregates usage.
- `web/kline.py` — uses dataset `TaiwanStockPrice` (raw price; `TaiwanStockPriceAdj` 還原 needs Backer despite what the docs imply). Caches in `kline` table; only fetches the missing tail.
- `web/chip.py` — `TaiwanStockInstitutionalInvestorsBuySell` + `TaiwanStockMarginPurchaseShortSale`. Aggregates institutional `buy - sell` per (foreign/trust/dealer) into the `institutional` table; stores `Margin/ShortSaleTodayBalance` per day.
- `web/cb.py` — 可轉換公司債 (CB) issuance data from the **TPEx open API** `bond_ISSBD5_data` (public, no auth, one request returns all listed CBs). `ensure_cb()` caches the snapshot in the `cb` table (refreshes once/day); `get_cb(code, active_only=True)` returns a stock's CBs (掛牌中 + 未到期). `conv_price` is the **發行時轉換價** (at issuance) — does NOT reflect later anti-dilution adjustments, and there is no free API for the adjusted/current price.
- `web/names.py` — stock code → 中文股名, cached in `stock_names` from FinMind `TaiwanStockInfo` (one request). `ensure_names()` / `get_names(codes)`; surfaced via `/api/events/summary`.
- `web/backtest.py` — anchor = first trading day **strictly after** `filed_at.date()`, T+0 uses that day's **open**; T+N uses the **close** N trading days later. Chip window = ±5 trading days around anchor. Stats are bucketed by `類別/狀態` (公司債|增資 / 稿本|生效).
- `web/scraper.py` — unified 上市+上櫃 scraper (see Scripts). `run_scrape(log, roc_year, seamon=None, markets)` → whole-year (seamon="") or single-month, writes straight to `events` via `db.import_rows`.
- `web/scraper_job.py` — `start_job(roc_year=None, seamon=None)` runs `scraper.run_scrape` in a background thread (defaults to the current ROC month for ongoing use), buffers log lines in memory + `scrape_jobs`.
- `web/app.py` — FastAPI; on startup runs `init_db()` only (no CSV import).
- `frontend/` — React + TS + Vite + Tailwind + shadcn/ui. Bundled to a single `bundle.html` via `web-artifacts-builder` skill; FastAPI serves that at `/`.

### API surface

- `GET /api/events?month=&code=&doc_type=` — filtered event rows (now include `market`, `case_status`, `file_link`)
- `GET /api/events/summary` — distinct codes (with count + last filed + 中文股名 `name`), available months, doc_types
- `GET /api/cb/{code}` — 流通中可轉債 (轉換價＋發行資訊) from TPEx ISSBD5; conversion-price lines on the K-line + info panel below
- `POST /api/scrape?year=&month=` → `{job_id}` (no params = current ROC month; `year` only = whole-year backfill); `GET /api/scrape/{id}?since=N` for polling
- `POST /api/update-codes` — refresh `codes/listed.csv` + `codes/otc.csv` from TWSE ISIN
- `GET /api/kline/{code}?days=N`
- `GET /api/backtest/{code}` — events + T+N returns + chip window aggregates + stats per doc_type
- `GET /api/quota` — FinMind remaining requests across all tokens

### Required configuration

`.env` adds:

```
FINMIND_TOKENS=token1,token2,token3   # comma-separated; free tier = 600/hour each
```

### Things to watch for

- File and identifier names are Chinese; keep them as-is in code and tooling references.
- `old/` holds archived standalone scrapers + their PyInstaller artifacts; it is gitignored and not wired into anything. Don't import from it — the live scraper is `web/scraper.py`.
- `MM月data.csv` columns are **`code, doc_type, ROC datetime`** (not `[date, doc_type, file_id]` — earlier draft of this doc was wrong).
- SQLite has `detect_types=PARSE_DECLTYPES` on, so `DATE` columns come back as `datetime.date`. Convert to ISO strings before comparing with bisect on date strings.
- `TaiwanStockPriceAdj` is documented as Free with `data_id` but returns 400 ("Your level is register") for these accounts — use `TaiwanStockPrice` instead.
