"""可轉換公司債 (CB) issuance data, cached from the TPEx open API.

Source: https://www.tpex.org.tw/openapi/v1/bond_ISSBD5_data (轉(交)換債發行資料).
Public, no auth, returns a snapshot of all currently-listed CBs in one request.
conv_price is the 發行時轉換價 (at issuance) — it does NOT reflect later
anti-dilution adjustments; the adjusted/current price has no free API.
"""
from __future__ import annotations

import datetime as dt

import httpx

from . import db

ISSBD5_URL = "https://www.tpex.org.tw/openapi/v1/bond_ISSBD5_data"


def _ymd(s: str | None) -> str | None:
    """'20241210' → '2024-12-10'. Empty/invalid → None."""
    s = (s or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _num(s: str | None) -> float | None:
    try:
        v = float((s or "").strip())
        return v
    except (TypeError, ValueError):
        return None


def ensure_cb(force: bool = False) -> int:
    """Refresh the cb table from TPEx. No-op if already fetched today."""
    if not force:
        with db.connect() as conn:
            row = conn.execute("SELECT MAX(fetched_at) AS f FROM cb").fetchone()
        last = row["f"] if row else None
        if last and str(last)[:10] == dt.date.today().isoformat():
            with db.connect() as conn:
                return conn.execute("SELECT COUNT(*) AS n FROM cb").fetchone()["n"]

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(ISSBD5_URL, headers={"accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()

    now = dt.datetime.now().isoformat(timespec="seconds")
    rows = []
    for r in data:
        bond_code = (r.get("BondCode") or "").strip()
        if not bond_code:  # skip 私募 (no tradable code)
            continue
        rows.append((
            bond_code,
            (r.get("IssuerCode") or "").strip(),
            (r.get("ShortName") or "").strip(),
            _num(r.get("Conversion/ExchangePriceAtIssuance")),
            _ymd(r.get("Conversion/ExchangePeriodStartDate")),
            _ymd(r.get("Conversion/ExchangePeriodEndDate")),
            _ymd(r.get("IssueDate")),
            _ymd(r.get("MaturityDate")),
            _num(r.get("IssueAmount")),
            _num(r.get("OutstandingAmount")),
            _num(r.get("CouponRate")),
            _ymd(r.get("PutOptionDate")),
            _num(r.get("PutOptionPrice")),
            (r.get("ListingStatus") or "").strip(),
            now,
        ))

    with db.connect() as conn:
        conn.execute("DELETE FROM cb")
        conn.executemany(
            "INSERT OR REPLACE INTO cb (bond_code, stock_code, name, conv_price, "
            "conv_start, conv_end, issue_date, maturity_date, issue_amount, "
            "outstanding_amount, coupon_rate, put_date, put_price, listing_status, "
            "fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def get_cb(stock_code: str, active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM cb WHERE stock_code = ?"
    args: list = [stock_code]
    if active_only:
        sql += " AND listing_status = '2' AND (maturity_date IS NULL OR maturity_date >= ?)"
        args.append(dt.date.today().isoformat())
    sql += " ORDER BY conv_end DESC, issue_date DESC"
    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]
