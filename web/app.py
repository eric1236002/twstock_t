"""FastAPI application."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import backtest, cb, chip, codes, db, finmind, kline, names, news, scraper_job

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="twstock 稿本爬蟲 + K 線回測")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    removed = kline.cleanup_old() + chip.cleanup_old()
    if removed:
        import logging
        logging.getLogger(__name__).info("kline/chip cache cleanup: removed %d old rows", removed)


@app.get("/api/events")
def list_events(
    year: str | None = Query(None, description="西元 year 'YYYY' (filed_at)"),
    month: str | None = Query(None, description="source month 'MM'"),
    code: str | None = None,
    doc_type: str | None = None,
):
    sql = (
        "SELECT id, code, market, doc_type, case_status, file_link, filed_at, source_month "
        "FROM events WHERE 1=1"
    )
    args: list = []
    if year:
        sql += " AND substr(filed_at,1,4) = ?"
        args.append(year)
    if month:
        sql += " AND source_month = ?"
        args.append(month)
    if code:
        sql += " AND code = ?"
        args.append(code)
    if doc_type:
        sql += " AND doc_type = ?"
        args.append(doc_type)
    sql += " ORDER BY filed_at DESC LIMIT 5000"
    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/events/summary")
def events_summary():
    """Distinct codes with event counts + available months/doc_types."""
    with db.connect() as conn:
        codes = [
            dict(r)
            for r in conn.execute(
                "SELECT code, COUNT(*) AS n, MAX(filed_at) AS last_filed "
                "FROM events GROUP BY code ORDER BY last_filed DESC"
            )
        ]
        years = [r["y"] for r in conn.execute(
            "SELECT DISTINCT substr(filed_at,1,4) AS y FROM events ORDER BY y DESC"
        )]
        months = [r["source_month"] for r in conn.execute(
            "SELECT DISTINCT source_month FROM events "
            "WHERE source_month IS NOT NULL ORDER BY source_month"
        )]
        doc_types = [r["doc_type"] for r in conn.execute(
            "SELECT DISTINCT doc_type FROM events ORDER BY doc_type"
        )]
    # Attach 中文股名 (best-effort; FinMind quota may be exhausted)
    try:
        names.ensure_names()
        name_map = names.get_names([c["code"] for c in codes])
    except Exception:  # noqa: BLE001
        name_map = {}
    for c in codes:
        c["name"] = name_map.get(c["code"])
    return {"codes": codes, "years": years, "months": months, "doc_types": doc_types}


@app.post("/api/scrape")
def start_scrape(
    year: int | None = Query(None, description="ROC year, e.g. 115; omit for current"),
    month: int | None = Query(None, ge=1, le=12, description="ROC month; omit for whole year when year given"),
):
    # default (no params): current ROC month. year given + no month: whole-year backfill.
    job_id = scraper_job.start_job(roc_year=year, seamon=month)
    return {"job_id": job_id}


@app.post("/api/update-codes")
def update_codes():
    return codes.update_code_lists()


@app.get("/api/scrape/{job_id}")
def get_scrape(job_id: int, since: int = 0):
    job = scraper_job.get_job(job_id, since=since)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/scrape")
def list_scrape_jobs():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, status, started_at, finished_at, rows_inserted "
            "FROM scrape_jobs ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/kline/{code}")
def get_kline(code: str, days: int = Query(730, ge=30, le=365 * 10)):
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    try:
        data = kline.get_kline(code, start=start, end=end)
    except finmind.QuotaExhausted as e:
        raise HTTPException(429, str(e))
    except finmind.FinMindError as e:
        raise HTTPException(502, f"FinMind error: {e}")
    return {"code": code, "data": data}


@app.get("/api/backtest/{code}")
def get_backtest(code: str):
    try:
        return backtest.event_returns(code)
    except finmind.QuotaExhausted as e:
        raise HTTPException(429, str(e))
    except finmind.FinMindError as e:
        raise HTTPException(502, f"FinMind error: {e}")


@app.get("/api/chip/{code}")
def get_chip(code: str, days: int = Query(540, ge=30, le=365 * 10)):
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    try:
        chip.ensure_institutional(code, start, end)
        chip.ensure_margin(code, start, end)
    except finmind.QuotaExhausted as e:
        raise HTTPException(429, str(e))
    except finmind.FinMindError as e:
        raise HTTPException(502, f"FinMind error: {e}")
    return {"code": code, "data": chip.daily_series(code, start, end)}


@app.get("/api/cb/{code}")
def get_cb(code: str):
    """流通中可轉債（轉換價 + 發行資訊），來源 TPEx ISSBD5。"""
    try:
        cb.ensure_cb()
    except Exception:  # noqa: BLE001
        pass
    return {"code": code, "data": cb.get_cb(code)}


def _bg_prefetch_kline(codes: list[str]) -> None:
    """Background: fetch recent kline for stocks that have no cached price data."""
    today = dt.date.today()
    start = today - dt.timedelta(days=90)
    for code in codes:
        try:
            kline.get_kline(code, start=start, end=today)
        except Exception:
            pass


@app.get("/api/overview")
def get_overview(
    background_tasks: BackgroundTasks,
    year: str | None = Query(None),
    month: str | None = Query(None),
):
    """Overview: all stocks with events for the given month/year, with cached price change."""
    sql = "SELECT code, market, doc_type, filed_at FROM events WHERE 1=1"
    args: list = []
    if year:
        sql += " AND substr(filed_at,1,4) = ?"
        args.append(year)
    if month:
        sql += " AND source_month = ?"
        args.append(month)

    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
        years = [r["y"] for r in conn.execute(
            "SELECT DISTINCT substr(filed_at,1,4) AS y FROM events ORDER BY y DESC"
        )]
        months = [r["source_month"] for r in conn.execute(
            "SELECT DISTINCT source_month FROM events "
            "WHERE source_month IS NOT NULL ORDER BY source_month"
        )]

    code_data: dict = {}
    for r in rows:
        code = r["code"]
        if code not in code_data:
            code_data[code] = {
                "code": code,
                "market": r["market"],
                "has_bond": False,
                "has_issue": False,
                "event_count": 0,
                "last_event": r["filed_at"],
            }
        d = code_data[code]
        d["event_count"] += 1
        if r["filed_at"] > d["last_event"]:
            d["last_event"] = r["filed_at"]
        if "公司債" in r["doc_type"]:
            d["has_bond"] = True
        if "增資" in r["doc_type"]:
            d["has_issue"] = True

    codes_list = list(code_data.keys())

    # Recent 20-trading-day price change from kline cache — no new API calls
    price_changes: dict[str, float | None] = {}
    if codes_list:
        with db.connect_local() as conn:
            placeholders = ",".join("?" * len(codes_list))
            kline_rows = conn.execute(
                f"SELECT code, close FROM kline "
                f"WHERE code IN ({placeholders}) "
                f"AND date >= date('now', '-60 days') "
                f"ORDER BY code, date",
                codes_list,
            ).fetchall()
        by_code: dict[str, list] = {}
        for r in kline_rows:
            by_code.setdefault(r["code"], []).append(r["close"])
        for code, closes in by_code.items():
            if len(closes) >= 20 and closes[-20]:
                price_changes[code] = round(
                    (closes[-1] - closes[-20]) / closes[-20] * 100, 2
                )

    # Background: quietly prefetch kline for up to 5 stocks missing price data
    missing = [c for c in codes_list if c not in price_changes]
    if missing:
        background_tasks.add_task(_bg_prefetch_kline, missing[:5])

    try:
        names.ensure_names()
        name_map = names.get_names(codes_list)
    except Exception:  # noqa: BLE001
        name_map = {}

    result = []
    for code, d in code_data.items():
        result.append({
            "code": code,
            "market": d["market"],
            "name": name_map.get(code),
            "has_bond": d["has_bond"],
            "has_issue": d["has_issue"],
            "event_count": d["event_count"],
            "last_event": d["last_event"],
            "price_change_pct": price_changes.get(code),
        })

    result.sort(key=lambda x: (x["price_change_pct"] is None, -(x["price_change_pct"] or 0)))

    with_price = [x["price_change_pct"] for x in result if x["price_change_pct"] is not None]
    return {
        "stocks": result,
        "summary": {
            "total": len(result),
            "cb_count": sum(1 for x in result if x["has_bond"]),
            "issue_count": sum(1 for x in result if x["has_issue"]),
            "avg_price_change": round(sum(with_price) / len(with_price), 2) if with_price else None,
        },
        "years": years,
        "months": months,
    }


@app.get("/api/news/{code}")
def get_news(code: str, center: str = Query(..., description="申報日 YYYY-MM-DD")):
    try:
        center_date = dt.date.fromisoformat(center)
    except ValueError:
        raise HTTPException(400, "Invalid date format")
    try:
        news.ensure_news(code, center_date)
    except finmind.QuotaExhausted as e:
        raise HTTPException(429, str(e))
    return {"code": code, "data": news.get_news(code, center_date)}


@app.get("/api/quota")
def quota():
    return finmind.quota_remaining()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "bundle.html")
