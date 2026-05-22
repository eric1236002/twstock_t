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


def _missing_ranges(table: str, code: str, start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    """Ranges within [start, end] not yet covered by cache.

    Cache coverage is treated as the contiguous [min, max] span (we only ever
    fetch contiguous ranges). Returns the head gap (before min) and/or tail gap
    (after max) that still need fetching.
    """
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT MIN(date) AS mn, MAX(date) AS mx FROM {table} WHERE code=?",
            (code,),
        ).fetchone()
    if not row or not row["mn"]:
        return [(start, end)]
    mn = dt.date.fromisoformat(str(row["mn"]))
    mx = dt.date.fromisoformat(str(row["mx"]))
    gaps: list[tuple[dt.date, dt.date]] = []
    if start < mn:
        gaps.append((start, mn - dt.timedelta(days=1)))
    if end > mx:
        gaps.append((mx + dt.timedelta(days=1), end))
    return gaps


def ensure_institutional(code: str, start: dt.date, end: dt.date) -> int:
    inserted = 0
    for s, e in _missing_ranges("institutional", code, start, end):
        rows = finmind.get_data(
            INST_DATASET,
            data_id=code,
            start_date=s.isoformat(),
            end_date=e.isoformat(),
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
            continue
        with db.connect() as conn:
            cur = conn.executemany(
                "INSERT OR REPLACE INTO institutional "
                "(code, date, foreign_net, trust_net, dealer_net) VALUES (?, ?, ?, ?, ?)",
                [
                    (code, d, v["foreign"], v["trust"], v["dealer"])
                    for d, v in agg.items()
                ],
            )
            inserted += cur.rowcount
    return inserted


# ---- Margin / short -------------------------------------------------------

MARGIN_DATASET = "TaiwanStockMarginPurchaseShortSale"


def ensure_margin(code: str, start: dt.date, end: dt.date) -> int:
    inserted = 0
    for s, e in _missing_ranges("margin", code, start, end):
        rows = finmind.get_data(
            MARGIN_DATASET,
            data_id=code,
            start_date=s.isoformat(),
            end_date=e.isoformat(),
        )
        if not rows:
            continue
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
            inserted += cur.rowcount
    return inserted


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


# ---- Daily series (for sub-pane histograms) ------------------------------

def daily_series(code: str, start: dt.date, end: dt.date) -> list[dict]:
    """Per-day institutional nets (張) + margin/short balance, merged by date."""
    s, e = start.isoformat(), end.isoformat()
    with db.connect() as conn:
        inst = conn.execute(
            "SELECT date, foreign_net, trust_net, dealer_net FROM institutional "
            "WHERE code=? AND date BETWEEN ? AND ? ORDER BY date",
            (code, s, e),
        ).fetchall()
        mg = conn.execute(
            "SELECT date, margin_balance, short_balance FROM margin "
            "WHERE code=? AND date BETWEEN ? AND ? ORDER BY date",
            (code, s, e),
        ).fetchall()

    merged: dict[str, dict] = {}
    for r in inst:
        d = r["date"].isoformat() if isinstance(r["date"], dt.date) else r["date"]
        f = (r["foreign_net"] or 0) / 1000
        t = (r["trust_net"] or 0) / 1000
        de = (r["dealer_net"] or 0) / 1000
        merged[d] = {
            "date": d,
            "foreign_net": round(f),
            "trust_net": round(t),
            "dealer_net": round(de),
            "total_net": round(f + t + de),
            "margin_balance": None,
            "short_balance": None,
        }
    for r in mg:
        d = r["date"].isoformat() if isinstance(r["date"], dt.date) else r["date"]
        row = merged.setdefault(d, {
            "date": d, "foreign_net": 0, "trust_net": 0,
            "dealer_net": 0, "total_net": 0,
            "margin_balance": None, "short_balance": None,
        })
        row["margin_balance"] = r["margin_balance"]
        row["short_balance"] = r["short_balance"]

    return [merged[k] for k in sorted(merged)]
