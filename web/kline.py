"""Fetch K-line via FinMind TaiwanStockPriceAdj with SQLite cache."""
from __future__ import annotations

import datetime as dt
import logging

from . import db, finmind

logger = logging.getLogger(__name__)
DATASET = "TaiwanStockPrice"  # PriceAdj (還原) requires backer; raw price is free

# Per-code "slot" of the last tail fetch.
# Slot = (date, evening) where evening=True means hour >= 18.
# Before 18:00 fetch once (cap at yesterday); after 18:00 allow one more fetch (cap at today).
_last_tail_slot: dict[str, tuple[dt.date, bool]] = {}


def _current_slot() -> tuple[dt.date, bool]:
    now = dt.datetime.now()
    return (now.date(), now.hour >= 18)


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
    """Fetch FinMind for any missing date range.

    Tail fetch policy:
    - Before 18:00: cap at yesterday, fetch at most once per (day, morning) slot.
    - After 18:00:  cap at today,     fetch at most once per (day, evening) slot.
    This avoids hammering FinMind quota while still picking up the day's close.
    """
    today = dt.date.today()
    now = dt.datetime.now()
    # Effective upper bound depends on time-of-day
    effective_end = min(end, today if now.hour >= 18 else today - dt.timedelta(days=1))

    bounds = _cached_bounds(code)
    if bounds is None:
        return _fetch_into_cache(code, start, effective_end)

    mn, mx = bounds
    inserted = 0

    if start < mn:  # backfill older head (no rate-limit needed)
        inserted += _fetch_into_cache(code, start, mn - dt.timedelta(days=1))

    if effective_end > mx:
        slot = _current_slot()
        if _last_tail_slot.get(code) != slot:
            inserted += _fetch_into_cache(code, mx + dt.timedelta(days=1), effective_end)
            _last_tail_slot[code] = slot
        else:
            logger.debug("kline tail skipped (slot already fetched): %s mx=%s", code, mx)

    return inserted


def cleanup_old(keep_days: int = 30) -> int:
    """Delete all kline rows for codes not accessed in keep_days days.
    Returns the number of deleted rows."""
    cutoff = (dt.date.today() - dt.timedelta(days=keep_days)).isoformat()
    with db.connect_local() as conn:
        stale = [
            r["code"] for r in conn.execute(
                "SELECT code FROM kline_meta WHERE last_accessed < ?", (cutoff,)
            ).fetchall()
        ]
        if not stale:
            return 0
        ph = ",".join("?" * len(stale))
        cur = conn.execute(f"DELETE FROM kline WHERE code IN ({ph})", stale)
        conn.execute(f"DELETE FROM kline_meta WHERE code IN ({ph})", stale)
    n = cur.rowcount
    if n:
        logger.info("kline cleanup: removed %d rows for %d stale codes", n, len(stale))
    return n


def get_kline(code: str, start: dt.date | None = None, end: dt.date | None = None) -> list[dict]:
    """Return cached OHLC rows, refreshing only the missing tail."""
    if end is None:
        end = dt.date.today()
    if start is None:
        start = end - dt.timedelta(days=365 * 2)
    ensure_range(code, start, end)
    with db.connect_local() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kline_meta (code, last_accessed) VALUES (?, ?)",
            (code, dt.date.today().isoformat()),
        )
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
