"""CB 策略雷達 — current watchlist from the CB near-conversion strategy.

Screens currently-listed CBs (cached cb/kline/institutional/margin, no FinMind at
request time) for the setup that backtested best:
  * latest close within ±5% of a live CB's 發行轉換價 (best when still *below*)
  * that CB within 180d of maturity/put (issuer motive to push conversion)
  * confirmed = 投信 net buyer over the last 5 trading days (≈doubled the 月內噴≥20% rate)
Caveats live in the backtest report: in-sample, recent-regime, conv_price unadjusted,
survivorship. This is a watchlist, not a buy list.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
from collections import defaultdict

from . import cb as cb_mod
from . import chip, db, kline

logger = logging.getLogger(__name__)

BAND = 0.05
DEADLINE_DAYS = 180
LB = 5  # trailing trading days for the 投信 / 融券 check
REFRESH_LOOKBACK_DAYS = 90  # incremental: only the missing tail is actually fetched


def _to_date(v) -> dt.date | None:
    """DATE columns come back as date (PARSE_DECLTYPES); others as str. Normalize."""
    if v is None:
        return None
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def cb_radar() -> dict:
    try:
        cb_mod.ensure_cb()  # daily snapshot refresh (no-op if already today)
    except Exception:  # noqa: BLE001
        pass

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT stock_code, name, conv_price, conv_start, conv_end, maturity_date, "
            "put_date FROM cb WHERE listing_status='2' AND conv_price>0 "
            "AND COALESCE(outstanding_amount,0)>0"
        ).fetchall()
        names = {r["code"]: r["name"] for r in conn.execute("SELECT code, name FROM stock_names")}

        by_stock: dict[str, list] = defaultdict(list)
        for r in rows:
            by_stock[r["stock_code"]].append(r)

        cands = []
        for code, lst in by_stock.items():
            krow = conn.execute(
                "SELECT date, close FROM kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
            ).fetchone()
            if not krow or not krow["close"]:
                continue
            today_d = _to_date(krow["date"]); px = krow["close"]
            if today_d is None:
                continue

            applic = []
            for bb in lst:
                cs = _to_date(bb["conv_start"]); ce = _to_date(bb["conv_end"])
                if (cs is None or cs <= today_d) and (ce is None or today_d <= ce):
                    applic.append(bb)
            if not applic:
                continue
            b = min(applic, key=lambda x: abs(px / x["conv_price"] - 1))
            conv_pos = px / b["conv_price"] - 1
            if abs(conv_pos) > BAND:
                continue
            dls = [x for x in (_to_date(b["maturity_date"]), _to_date(b["put_date"])) if x]
            up = [(x - today_d).days for x in dls if x >= today_d]
            if not up or min(up) >= DEADLINE_DAYS:
                continue

            trs = conn.execute(
                "SELECT trust_net FROM institutional WHERE code=? ORDER BY date DESC LIMIT ?",
                (code, LB),
            ).fetchall()
            trust5 = sum(r["trust_net"] for r in trs) if trs else None
            sh = conn.execute(
                "SELECT short_balance FROM margin WHERE code=? ORDER BY date DESC LIMIT ?",
                (code, LB + 1),
            ).fetchall()
            short_up = len(sh) > LB and sh[0]["short_balance"] > sh[LB]["short_balance"]

            cands.append({
                "code": code,
                "name": names.get(code, b["name"]),
                "as_of": today_d.isoformat(),
                "close": px,
                "conv_price": b["conv_price"],
                "conv_pos_pct": round(conv_pos * 100, 1),
                "days_to_deadline": min(up),
                "cb_name": b["name"],
                "trust5_zhang": round(trust5 / 1000) if trust5 is not None else None,
                "short_up": short_up,
                "confirmed": trust5 is not None and trust5 > 0,
            })

    # confirmed first, then closest to conversion price
    cands.sort(key=lambda c: (not c["confirmed"], abs(c["conv_pos_pct"])))
    as_of = max((c["as_of"] for c in cands), default=None)
    return {"as_of": as_of, "candidates": cands}


# ---- Manual refresh (triggered by the 重新整理 button) ----------------------
# The radar reads only cached data; this job tops that cache up to the latest
# trading day. Fetches are incremental (kline/chip ensure_* only request the
# missing tail), so when data is already current this is nearly free. Runs in a
# background thread so the request returns immediately; the page polls status.

_state = {"running": False, "done": 0, "total": 0, "last_updated": None, "error": None}
_lock = threading.Lock()


def refresh_status() -> dict:
    return dict(_state)


def _active_cb_stocks() -> list[str]:
    with db.connect() as conn:
        return [r["stock_code"] for r in conn.execute(
            "SELECT DISTINCT stock_code FROM cb "
            "WHERE listing_status='2' AND conv_price>0 AND COALESCE(outstanding_amount,0)>0"
        )]


def _run_refresh() -> None:
    try:
        try:
            cb_mod.ensure_cb()
        except Exception as e:  # noqa: BLE001
            logger.warning("radar refresh: ensure_cb failed: %s", e)
        codes = _active_cb_stocks()
        _state["total"] = len(codes)
        end = dt.date.today()
        start = end - dt.timedelta(days=REFRESH_LOOKBACK_DAYS)
        for code in codes:
            try:
                kline.get_kline(code, start=start, end=end)
                chip.ensure_institutional(code, start, end)
                chip.ensure_margin(code, start, end)
            except Exception as e:  # noqa: BLE001
                logger.debug("radar refresh: %s failed: %s", code, e)
            _state["done"] += 1
        _state["last_updated"] = dt.datetime.now().isoformat(timespec="seconds")
        _state["error"] = None
    except Exception as e:  # noqa: BLE001
        _state["error"] = str(e)
        logger.exception("radar refresh failed")
    finally:
        _state["running"] = False


def start_refresh() -> dict:
    """Start a background universe refresh if one isn't already running."""
    with _lock:
        if _state["running"]:
            return dict(_state)
        _state.update(running=True, done=0, total=0, error=None)
    threading.Thread(target=_run_refresh, name="radar-refresh", daemon=True).start()
    return dict(_state)
