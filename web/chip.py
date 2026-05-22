"""Chip-side data (institutional investors, margin) from FinMind."""
from __future__ import annotations

import datetime as dt
import logging

from . import db, finmind

logger = logging.getLogger(__name__)


# ---- Institutional investors ---------------------------------------------

INST_DATASET = "TaiwanStockInstitutionalInvestorsBuySell"

_FOREIGN_KEYS = {"Foreign_Investor", "Foreign_Dealer_Self"}
_TRUST_KEYS = {"Investment_Trust"}
_DEALER_KEYS = {"Dealer_self", "Dealer_Hedging", "Dealer"}


def _classify_institution(name: str) -> str | None:
    if name in _FOREIGN_KEYS:
        return "foreign"
    if name in _TRUST_KEYS:
        return "trust"
    if name in _DEALER_KEYS:
        return "dealer"
    return None


def _cached_inst_max(code: str) -> dt.date | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS mx FROM institutional WHERE code=?", (code,)
        ).fetchone()
    return dt.date.fromisoformat(row["mx"]) if row and row["mx"] else None


def ensure_institutional(code: str, start: dt.date, end: dt.date) -> int:
    mx = _cached_inst_max(code)
    fetch_start = max(start, mx + dt.timedelta(days=1)) if mx else start
    if fetch_start > end:
        return 0
    rows = finmind.get_data(
        INST_DATASET,
        data_id=code,
        start_date=fetch_start.isoformat(),
        end_date=end.isoformat(),
    )
    # Aggregate per date: net = buy - sell, per category
    agg: dict[str, dict[str, int]] = {}
    for r in rows:
        date = r.get("date")
        if not date:
            continue
        cat = _classify_institution(r.get("name", ""))
        if not cat:
            continue
        bucket = agg.setdefault(date, {"foreign": 0, "trust": 0, "dealer": 0})
        net = int((r.get("buy") or 0)) - int((r.get("sell") or 0))
        bucket[cat] += net
    if not agg:
        return 0
    with db.connect() as conn:
        cur = conn.executemany(
            "INSERT OR REPLACE INTO institutional "
            "(code, date, foreign_net, trust_net, dealer_net) VALUES (?, ?, ?, ?, ?)",
            [
                (code, d, v["foreign"], v["trust"], v["dealer"])
                for d, v in agg.items()
            ],
        )
        return cur.rowcount


# ---- Margin / short -------------------------------------------------------

MARGIN_DATASET = "TaiwanStockMarginPurchaseShortSale"


def _cached_margin_max(code: str) -> dt.date | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS mx FROM margin WHERE code=?", (code,)
        ).fetchone()
    return dt.date.fromisoformat(row["mx"]) if row and row["mx"] else None


def ensure_margin(code: str, start: dt.date, end: dt.date) -> int:
    mx = _cached_margin_max(code)
    fetch_start = max(start, mx + dt.timedelta(days=1)) if mx else start
    if fetch_start > end:
        return 0
    rows = finmind.get_data(
        MARGIN_DATASET,
        data_id=code,
        start_date=fetch_start.isoformat(),
        end_date=end.isoformat(),
    )
    if not rows:
        return 0
    with db.connect() as conn:
        cur = conn.executemany(
            "INSERT OR REPLACE INTO margin "
            "(code, date, margin_balance, short_balance) VALUES (?, ?, ?, ?)",
            [
                (
                    code,
                    r["date"],
                    int(r.get("MarginPurchaseTodayBalance") or 0),
                    int(r.get("ShortSaleTodayBalance") or 0),
                )
                for r in rows
                if r.get("date")
            ],
        )
        return cur.rowcount


# ---- Window aggregation around an event date -----------------------------

def institutional_window(code: str, start: str, end: str) -> dict:
    """Sum net buys across [start, end] inclusive."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(foreign_net),0) AS f, "
            "COALESCE(SUM(trust_net),0) AS t, "
            "COALESCE(SUM(dealer_net),0) AS d "
            "FROM institutional WHERE code=? AND date BETWEEN ? AND ?",
            (code, start, end),
        ).fetchone()
    f, t, d = row["f"], row["t"], row["d"]
    return {
        "foreign_net": f, "trust_net": t, "dealer_net": d,
        "total_net": f + t + d,
    }


def margin_change(code: str, start: str, end: str) -> dict:
    """Margin/short balance delta between first and last available day in window."""
    with db.connect() as conn:
        first = conn.execute(
            "SELECT margin_balance, short_balance FROM margin "
            "WHERE code=? AND date BETWEEN ? AND ? ORDER BY date LIMIT 1",
            (code, start, end),
        ).fetchone()
        last = conn.execute(
            "SELECT margin_balance, short_balance FROM margin "
            "WHERE code=? AND date BETWEEN ? AND ? ORDER BY date DESC LIMIT 1",
            (code, start, end),
        ).fetchone()
    if not first or not last:
        return {"margin_delta": None, "short_delta": None}
    return {
        "margin_delta": last["margin_balance"] - first["margin_balance"],
        "short_delta": last["short_balance"] - first["short_balance"],
    }
