"""Stock news from FinMind TaiwanStockNews — fetched per calendar day, cached in SQLite."""
from __future__ import annotations

import datetime as dt
import logging

from . import db, finmind

logger = logging.getLogger(__name__)
DATASET = "TaiwanStockNews"


def _is_fetched(code: str, date: dt.date) -> bool:
    with db.connect_local() as conn:
        row = conn.execute(
            "SELECT 1 FROM news_fetched WHERE code=? AND date=?",
            (code, date.isoformat()),
        ).fetchone()
    return row is not None


def _fetch_day(code: str, date: dt.date) -> int:
    """Fetch one day of news from FinMind and cache. Returns inserted count."""
    if date > dt.date.today():
        return 0
    rows = finmind.get_data(DATASET, data_id=code, start_date=date.isoformat())
    inserted = 0
    with db.connect_local() as conn:
        for r in rows:
            published = (r.get("date") or "")[:19]
            if not published:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO news (code, published_at, title, source, link) "
                "VALUES (?, ?, ?, ?, ?)",
                (code, published, r.get("title"), r.get("source"), r.get("link")),
            )
            inserted += cur.rowcount
        conn.execute(
            "INSERT OR IGNORE INTO news_fetched (code, date) VALUES (?, ?)",
            (code, date.isoformat()),
        )
    return inserted


def ensure_news(code: str, center: dt.date, window: int = 5) -> None:
    """Fetch missing days in [center-window, center+window]. Skips already-cached days."""
    for i in range(-window, window + 1):
        d = center + dt.timedelta(days=i)
        if d > dt.date.today():
            break
        if not _is_fetched(code, d):
            try:
                _fetch_day(code, d)
            except finmind.QuotaExhausted:
                raise
            except Exception as exc:
                logger.warning("news fetch failed %s %s: %s", code, d, exc)


def get_news(code: str, center: dt.date, window: int = 5) -> list[dict]:
    """Return cached news items sorted by time for the window around center."""
    start = (center - dt.timedelta(days=window)).isoformat()
    end = (center + dt.timedelta(days=window)).isoformat()
    with db.connect_local() as conn:
        rows = conn.execute(
            "SELECT published_at, title, source, link FROM news "
            "WHERE code=? AND date(published_at) BETWEEN ? AND ? "
            "ORDER BY published_at",
            (code, start, end),
        ).fetchall()
    return [dict(r) for r in rows]
