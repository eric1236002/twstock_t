"""Event backtest: anchor = next trading day's open. T+N = close after N trading days."""
from __future__ import annotations

import datetime as dt
from bisect import bisect_left

from . import chip, db, kline

WINDOWS = [1, 5, 20, 60]
CHIP_WINDOW_DAYS = 5  # ±5 trading days around event


def _event_status(ev) -> str:
    """稿本 (draft) vs 生效 (effective) — mirrors the frontend marker logic."""
    cs = ev["case_status"]
    if cs == "生效":
        return "生效"
    if not cs and "稿本" not in ev["doc_type"]:
        return "生效"
    return "稿本"


def _next_trading_idx(dates: list[str], target: dt.date) -> int | None:
    """First index with date > target (strict next trading day)."""
    iso = target.isoformat()
    i = bisect_left(dates, iso)
    # if dates[i] == target, we want strictly after — bump
    if i < len(dates) and dates[i] == iso:
        i += 1
    return i if i < len(dates) else None


def event_returns(code: str) -> dict:
    with db.connect() as conn:
        events = conn.execute(
            "SELECT id, doc_type, case_status, file_link, market, filed_at "
            "FROM events WHERE code=? ORDER BY filed_at",
            (code,),
        ).fetchall()

    if not events:
        return {"code": code, "events": [], "stats": {}}

    earliest = dt.datetime.fromisoformat(events[0]["filed_at"]).date()
    latest = dt.datetime.fromisoformat(events[-1]["filed_at"]).date()
    start = earliest - dt.timedelta(days=30)
    end = min(dt.date.today(), latest + dt.timedelta(days=180))

    ohlc = kline.get_kline(code, start=start, end=end)
    # Prefetch chip data for same range (single FinMind call each, cached after)
    try:
        chip.ensure_institutional(code, start, end)
        chip.ensure_margin(code, start, end)
    except Exception as e:  # noqa: BLE001
        # Chip data is optional; don't fail backtest if quota out
        import logging
        logging.getLogger(__name__).warning("chip ensure failed: %s", e)

    dates = [r["date"] for r in ohlc]
    opens = [r["open"] for r in ohlc]
    closes = [r["close"] for r in ohlc]

    event_rows = []
    for ev in events:
        filed = dt.datetime.fromisoformat(ev["filed_at"])
        filed_date = filed.date()
        anchor_idx = _next_trading_idx(dates, filed_date)

        item: dict = {
            "id": ev["id"],
            "doc_type": ev["doc_type"],
            "case_status": ev["case_status"],
            "file_link": ev["file_link"],
            "market": ev["market"],
            "filed_at": ev["filed_at"],
            "anchor_date": None,
            "anchor_open": None,
            "returns": {},
            "chip": {},
        }

        if anchor_idx is not None:
            anchor_date = dates[anchor_idx]
            anchor_open = opens[anchor_idx]
            item["anchor_date"] = anchor_date
            item["anchor_open"] = anchor_open

            for w in WINDOWS:
                j = anchor_idx + w
                if 0 <= j < len(dates) and anchor_open:
                    ret = (closes[j] - anchor_open) / anchor_open * 100
                    item["returns"][f"T+{w}"] = {
                        "date": dates[j],
                        "close": closes[j],
                        "return_pct": round(ret, 2),
                    }

            # Chip window: ±5 trading days around anchor
            lo = max(0, anchor_idx - CHIP_WINDOW_DAYS)
            hi = min(len(dates) - 1, anchor_idx + CHIP_WINDOW_DAYS)
            win_start, win_end = dates[lo], dates[hi]
            inst = chip.institutional_window(code, win_start, win_end)
            mg = chip.margin_change(code, win_start, win_end)
            item["chip"] = {
                "window": [win_start, win_end],
                "institutional": inst,
                "margin": mg,
            }

        event_rows.append(item)

    # Aggregate stats per (category, status). Key = "公司債/稿本" etc. so the
    # 稿本 (draft) vs 生效 (effective) split shows up separately in the UI.
    stats: dict[str, dict] = {}
    for ev in event_rows:
        cat = "增資" if "增資" in ev["doc_type"] else "公司債"
        status = _event_status(ev)
        key = f"{cat}/{status}"
        bucket = stats.setdefault(key, {f"T+{w}": [] for w in WINDOWS})
        for w in WINDOWS:
            r = ev["returns"].get(f"T+{w}")
            if r:
                bucket[f"T+{w}"].append(r["return_pct"])

    agg = {}
    for d in sorted(stats):
        by_w = stats[d]
        agg[d] = {}
        for w_key, lst in by_w.items():
            if not lst:
                agg[d][w_key] = None
                continue
            wins = sum(1 for x in lst if x > 0)
            agg[d][w_key] = {
                "n": len(lst),
                "avg_return_pct": round(sum(lst) / len(lst), 2),
                "win_rate_pct": round(wins / len(lst) * 100, 1),
            }

    event_rows.sort(key=lambda x: x["filed_at"], reverse=True)
    return {"code": code, "events": event_rows, "stats": agg}
