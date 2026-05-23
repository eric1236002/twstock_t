"""SQLite / Turso schema and connection helpers.

When TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are present in the environment
the app uses Turso (libSQL); otherwise it falls back to the local SQLite file.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "twstock.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    market TEXT,
    doc_type TEXT NOT NULL,
    case_status TEXT,
    file_link TEXT,
    filed_at DATETIME NOT NULL,
    source_month TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, file_link)
);
CREATE INDEX IF NOT EXISTS idx_events_code ON events(code);
CREATE INDEX IF NOT EXISTS idx_events_filed_at ON events(filed_at);

CREATE TABLE IF NOT EXISTS stock_names (
    code TEXT PRIMARY KEY,
    name TEXT
);

CREATE TABLE IF NOT EXISTS cb (
    bond_code TEXT PRIMARY KEY,
    stock_code TEXT,
    name TEXT,
    conv_price REAL,
    conv_start DATE, conv_end DATE,
    issue_date DATE, maturity_date DATE,
    issue_amount REAL, outstanding_amount REAL,
    coupon_rate REAL,
    put_date DATE, put_price REAL,
    listing_status TEXT,
    fetched_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_cb_stock ON cb(stock_code);

CREATE TABLE IF NOT EXISTS scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    status TEXT NOT NULL,
    log TEXT,
    rows_inserted INTEGER DEFAULT 0
);
"""


def _turso_creds() -> tuple[str, str] | None:
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    return (url, token) if url and token else None


# ---------------------------------------------------------------------------
# libSQL row/cursor/connection wrappers (mimic sqlite3.Row + context manager)
# ---------------------------------------------------------------------------

class _Row:
    """Dict-like row wrapper for libsql_experimental rows (which are plain tuples)."""
    __slots__ = ("_d",)

    def __init__(self, description: Any, row: Sequence) -> None:
        self._d: dict[str, Any] = {col[0]: val for col, val in zip(description, row)}

    def __getitem__(self, key) -> Any:
        if isinstance(key, int):
            return list(self._d.values())[key]
        return self._d[key]

    def keys(self) -> list[str]:
        return list(self._d.keys())

    def __iter__(self):
        return iter(self._d.values())


class _Cursor:
    def __init__(self, inner: Any) -> None:
        self._c = inner

    @property
    def rowcount(self) -> int:
        return getattr(self._c, "rowcount", -1)

    @property
    def description(self) -> Any:
        return getattr(self._c, "description", None)

    def fetchall(self) -> list[_Row]:
        desc = self.description
        rows = self._c.fetchall()
        if not desc or not rows:
            return []
        return [_Row(desc, r) for r in rows]

    def fetchone(self) -> _Row | None:
        desc = self.description
        row = self._c.fetchone()
        if row is None or not desc:
            return None
        return _Row(desc, row)

    def __iter__(self):
        for r in self.fetchall():
            yield r


class _Conn:
    """Wraps libsql_experimental.Connection to behave like sqlite3.Connection."""

    def __init__(self, inner: Any) -> None:
        self._c = inner

    def execute(self, sql: str, params: Sequence = ()) -> _Cursor:
        return _Cursor(self._c.execute(sql, tuple(params)))

    def executemany(self, sql: str, params_seq) -> _Cursor:
        return _Cursor(self._c.executemany(sql, [tuple(p) for p in params_seq]))

    def executescript(self, script: str) -> None:
        for stmt in _split_sql(script):
            self._c.execute(stmt)
        self._c.commit()

    def commit(self) -> None:
        self._c.commit()

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, exc_type: Any, *_: Any) -> None:
        if exc_type is None:
            self._c.commit()


def _split_sql(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect() -> Any:
    """Main connection: Turso when configured, else local SQLite.
    Used by: events, cb, stock_names, scrape_jobs."""
    creds = _turso_creds()
    if creds:
        import libsql_experimental as libsql  # type: ignore[import]
        url, token = creds
        return _Conn(libsql.connect(url, auth_token=token))
    return connect_local()


def connect_local() -> sqlite3.Connection:
    """Always local SQLite — used by kline, institutional, margin."""
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


LOCAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS kline (
    code TEXT NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS institutional (
    code TEXT NOT NULL,
    date DATE NOT NULL,
    foreign_net INTEGER DEFAULT 0,
    trust_net INTEGER DEFAULT 0,
    dealer_net INTEGER DEFAULT 0,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS margin (
    code TEXT NOT NULL,
    date DATE NOT NULL,
    margin_balance INTEGER DEFAULT 0,
    short_balance INTEGER DEFAULT 0,
    PRIMARY KEY (code, date)
);
"""


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    with connect_local() as conn:
        conn.executescript(LOCAL_SCHEMA)


def rebuild_events() -> None:
    with connect() as conn:
        conn.execute("DROP TABLE IF EXISTS events")
        conn.executescript(SCHEMA)


def roc_to_iso(roc: str) -> str | None:
    m = re.match(r"\s*(\d{2,3})/(\d{1,2})/(\d{1,2})(?:\s+(\d{2}):(\d{2}):(\d{2}))?", roc)
    if not m:
        return None
    y = int(m.group(1)) + 1911
    mo, d = int(m.group(2)), int(m.group(3))
    if m.group(4):
        hh, mm, ss = int(m.group(4)), int(m.group(5)), int(m.group(6))
        return f"{y:04d}-{mo:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}"
    return f"{y:04d}-{mo:02d}-{d:02d} 00:00:00"


def import_rows(rows: list[dict]) -> int:
    inserted = 0
    with connect() as conn:
        for r in rows:
            filed_iso = roc_to_iso(r.get("filed_at", ""))
            if not filed_iso:
                continue
            source_month = filed_iso[5:7]
            cur = conn.execute(
                "INSERT OR IGNORE INTO events "
                "(code, market, doc_type, case_status, file_link, filed_at, source_month) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    r["code"],
                    r.get("market"),
                    r["doc_type"],
                    r.get("case_status"),
                    r.get("file_link"),
                    filed_iso,
                    source_month,
                ),
            )
            inserted += cur.rowcount
    return inserted
