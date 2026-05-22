"""FastAPI application."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import backtest, chip, db, finmind, kline, scraper_job

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="twstock 稿本爬蟲 + K 線回測")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    inserted = db.import_all_csvs()
    if inserted:
        print(f"[startup] imported {inserted} new events from CSVs")


@app.get("/api/events")
def list_events(
    month: str | None = Query(None, description="ROC source month 'MM'"),
    code: str | None = None,
    doc_type: str | None = None,
):
    sql = "SELECT id, code, doc_type, filed_at, source_month FROM events WHERE 1=1"
    args: list = []
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
        months = [r["source_month"] for r in conn.execute(
            "SELECT DISTINCT source_month FROM events "
            "WHERE source_month IS NOT NULL ORDER BY source_month"
        )]
        doc_types = [r["doc_type"] for r in conn.execute(
            "SELECT DISTINCT doc_type FROM events ORDER BY doc_type"
        )]
    return {"codes": codes, "months": months, "doc_types": doc_types}


@app.post("/api/scrape")
def start_scrape():
    job_id = scraper_job.start_job()
    return {"job_id": job_id}


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
def get_chip(code: str, days: int = Query(540, ge=30, le=365 * 5)):
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


@app.get("/api/quota")
def quota():
    return finmind.quota_remaining()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "bundle.html")
