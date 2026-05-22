# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Three standalone Python scrapers that pull Taiwanese securities filings and write monthly CSV/XLSX outputs. The scripts are shipped as Windows `.exe` bundles produced by PyInstaller — the `.spec` files in the repo root are the build descriptors, and `dist/` / `build/` are PyInstaller artifacts (gitignored). Source filenames are Traditional Chinese.

## Scripts

The listed-company scraper now lives **inside the web backend** at `web/scraper.py` (see Web app → Architecture). The standalone scripts below have been archived to `old/` (gitignored) as reference — they are no longer wired into anything.

- **`web/scraper.py`** — the live listed-company scraper. POSTs each code in `上市代碼/CODE.csv` to `https://doc.twse.com.tw/server-java/t57sb01`, runs 50 concurrent workers (`ThreadPoolExecutor`) with `tenacity` retry through the residential proxy, keeps `各類公司債(稿本)` / `增資發行(稿本)` rows, and writes `MM月data.csv` (`code, doc_type, ROC datetime`). Triggered via the `/api/scrape` endpoint.
- **old/上市稿本.py** — the original standalone version `web/scraper.py` was ported from. Archived reference.
- **old/上櫃稿本.py** — older OTC (`上櫃`) variant: single-threaded `requests`, sleep-every-10 throttle, no proxy/retries. Legacy reference.
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

- Input codes: `上市代碼/CODE.csv` — one stock code per line, no header.
- Output: `MM月data.csv` (UTF-8) in the working directory, three columns `[date, doc_type, file_id]` derived from columns 0, 5, 9 of the scraped table rows.
- The `seamon` POST field is `current_month - 1` (intentional — the site indexes by the previous month for current-month filings). `year` is ROC year (`西元 - 1911`).

## Web app (event browser + K-line backtest)

There is a FastAPI app under `web/` that browses the scraper events, triggers the scraper from the UI, and overlays event markers on K-line charts with T+N return stats. Reads CSV output into SQLite (`twstock.db`), pulls price + chip data from FinMind.

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

- `web/db.py` — SQLite schema (`events`, `kline`, `institutional`, `margin`, `scrape_jobs`) and CSV import (ROC date → ISO).
- `web/finmind.py` — FinMind REST client. Reads `FINMIND_TOKENS` (comma-separated) from `.env`; picks the least-used non-exhausted token each request; on `402`/`401` marks token exhausted until next top of hour. `get_data(dataset, **params)` is the only entry point. `quota_remaining()` aggregates usage.
- `web/kline.py` — uses dataset `TaiwanStockPrice` (raw price; `TaiwanStockPriceAdj` 還原 needs Backer despite what the docs imply). Caches in `kline` table; only fetches the missing tail.
- `web/chip.py` — `TaiwanStockInstitutionalInvestorsBuySell` + `TaiwanStockMarginPurchaseShortSale`. Aggregates institutional `buy - sell` per (foreign/trust/dealer) into the `institutional` table; stores `Margin/ShortSaleTodayBalance` per day.
- `web/backtest.py` — anchor = first trading day **strictly after** `filed_at.date()`, T+0 uses that day's **open**; T+N uses the **close** N trading days later. Chip window = ±5 trading days around anchor.
- `web/scraper.py` — the listed-company scraper, integrated in-process (ported from the standalone `上市稿本.py`). `run_listed_scrape(log)` POSTs each code in `上市代碼/CODE.csv` to the TWSE doc endpoint through the residential proxy (50 workers, tenacity retry, `verify=False`), writes `MM月data.csv`, and streams progress via the `log` callback.
- `web/scraper_job.py` — runs `web/scraper.run_listed_scrape` in a background thread (no subprocess), buffers log lines in memory + `scrape_jobs`, imports the resulting `MM月data.csv` into `events` on success.
- `web/app.py` — FastAPI; on startup runs `init_db()` and imports any `MM月data.csv` in repo root.
- `frontend/` — React + TS + Vite + Tailwind + shadcn/ui. Bundled to a single `bundle.html` via `web-artifacts-builder` skill; FastAPI serves that at `/`.

### API surface

- `GET /api/events?month=&code=&doc_type=` — filtered event rows
- `GET /api/events/summary` — distinct codes (with count + last filed), available months, doc_types
- `POST /api/scrape` → `{job_id}`; `GET /api/scrape/{id}?since=N` for polling (returns log tail)
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
