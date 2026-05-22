"""Fetch K-line via FinMind TaiwanStockPriceAdj with SQLite cache."""
from __future__ import annotations

import datetime as dt
import logging

from . import db, finmind

logger = logging.getLogger(__name__)
DATASET = "TaiwanStockPrice"  # PriceAdj (還原) requires backer; raw price is free


def _cached_max_date(code: str) -> dt.date | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS mx FROM kline WHERE code=?", (code,)
        ).fetchone()
    if row and row["mx"]:
        return dt.date.fromisoformat(row["mx"])
    return None


def _insert_rows(code: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    with db.connect() as conn:
        cur = conn.executemany(
            "INSERT OR REPLACE INTO kline (code, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    code,
                    r["date"],
                    float(r.get("open") or 0),
                    float(r.get("max") or 0),
                    float(r.get("min") or 0),
                    float(r.get("close") or 0),
                    int(r.get("Trading_Volume") or 0),
                )
                for r in rows
                if r.get("open") not in (None, "", 0, 0.0)
            ],
        )
        return cur.rowcount


def ensure_range(code: str, start: dt.date, end: dt.date) -> int:
    """Fetch FinMind for any missing date range. Single HTTP call (FinMind returns range)."""
    mx = _cached_max_date(code)
    fetch_start = max(start, (mx + dt.timedelta(days=1))) if mx else start
    if fetch_start > end:
        return 0
    data = finmind.get_data(
        DATASET,
        data_id=code,
        start_date=fetch_start.isoformat(),
        end_date=end.isoformat(),
    )
    return _insert_rows(code, data)


def get_kline(code: str, start: dt.date | None = None, end: dt.date | None = None) -> list[dict]:
    """Return cached OHLC rows, refreshing only the missing tail."""
    if end is None:
        end = dt.date.today()
    if start is None:
        start = end - dt.timedelta(days=365 * 2)
    ensure_range(code, start, end)
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM kline "
            "WHERE code=? AND date BETWEEN ? AND ? ORDER BY date",
            (code, start.isoformat(), end.isoformat()),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d["date"], dt.date):
            d["date"] = d["date"].isoformat()
        out.append(d)
    return out
