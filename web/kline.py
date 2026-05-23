"""Fetch K-line via FinMind TaiwanStockPriceAdj with SQLite cache."""
from __future__ import annotations

import datetime as dt
import logging

from . import db, finmind

logger = logging.getLogger(__name__)
DATASET = "TaiwanStockPrice"  # PriceAdj (還原) requires backer; raw price is free


def _cached_bounds(code: str) -> tuple[dt.date, dt.date] | None:
    with db.connect_local() as conn:
        row = conn.execute(
            "SELECT MIN(date) AS mn, MAX(date) AS mx FROM kline WHERE code=?", (code,)
        ).fetchone()
    if row and row["mn"] and row["mx"]:
        return dt.date.fromisoformat(str(row["mn"])), dt.date.fromisoformat(str(row["mx"]))
    return None


def _fetch_into_cache(code: str, start: dt.date, end: dt.date) -> int:
    if start > end:
        return 0
    data = finmind.get_data(
        DATASET, data_id=code, start_date=start.isoformat(), end_date=end.isoformat()
    )
    return _insert_rows(code, data)


def _insert_rows(code: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    with db.connect_local() as conn:
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
    """Fetch FinMind for any missing date range — backfills BOTH the older head
    and the newer tail so the cache always spans the full requested window."""
    bounds = _cached_bounds(code)
    if bounds is None:
        return _fetch_into_cache(code, start, end)
    mn, mx = bounds
    inserted = 0
    if start < mn:  # backfill older data before the cached minimum
        inserted += _fetch_into_cache(code, start, mn - dt.timedelta(days=1))
    if end > mx:  # fetch newer data after the cached maximum
        inserted += _fetch_into_cache(code, mx + dt.timedelta(days=1), end)
    return inserted


def get_kline(code: str, start: dt.date | None = None, end: dt.date | None = None) -> list[dict]:
    """Return cached OHLC rows, refreshing only the missing tail."""
    if end is None:
        end = dt.date.today()
    if start is None:
        start = end - dt.timedelta(days=365 * 2)
    ensure_range(code, start, end)
    with db.connect_local() as conn:
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
