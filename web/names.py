"""Stock code → 中文股名, cached in SQLite from FinMind TaiwanStockInfo."""
from __future__ import annotations

from . import db, finmind


def ensure_names(force: bool = False) -> int:
    """Populate stock_names from FinMind (one request). No-op if already cached."""
    if not force:
        with db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM stock_names").fetchone()
            if row["n"] > 0:
                return row["n"]

    data = finmind.get_data("TaiwanStockInfo")
    seen: dict[str, str] = {}
    for d in data:
        sid, name = d.get("stock_id"), d.get("stock_name")
        if sid and name:
            seen[sid] = name
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO stock_names (code, name) VALUES (?, ?)",
            list(seen.items()),
        )
    return len(seen)


def get_names(codes: list[str] | None = None) -> dict[str, str]:
    with db.connect() as conn:
        if codes:
            qs = ",".join("?" * len(codes))
            rows = conn.execute(
                f"SELECT code, name FROM stock_names WHERE code IN ({qs})", codes
            ).fetchall()
        else:
            rows = conn.execute("SELECT code, name FROM stock_names").fetchall()
    return {r["code"]: r["name"] for r in rows}
