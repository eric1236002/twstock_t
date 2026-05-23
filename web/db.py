"""SQLite schema and connection helpers.

Local SQLite is the primary store for all tables.
Turso (libSQL) is used as a backup: new events are synced there
asynchronously after each scrape, if TURSO_DATABASE_URL + TURSO_AUTH_TOKEN
are present in the environment.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "twstock.db"

# Full local schema — all tables live here.
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

CREATE TABLE IF NOT EXISTS kline_meta (
    code TEXT PRIMARY KEY,
    last_accessed DATE NOT NULL
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

CREATE TABLE IF NOT EXISTS news (
    code TEXT NOT NULL,
    published_at DATETIME NOT NULL,
    title TEXT,
    source TEXT,
    link TEXT,
    PRIMARY KEY (code, published_at, link)
);

CREATE TABLE IF NOT EXISTS news_fetched (
    code TEXT NOT NULL,
    date DATE NOT NULL,
    PRIMARY KEY (code, date)
);
"""

# Minimal Turso backup schema — only events need cloud backup.
_TURSO_SCHEMA = """
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
"""


def _turso_creds() -> tuple[str, str] | None:
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    return (url, token) if url and token else None


# ---------------------------------------------------------------------------
# libSQL wrappers (used only for Turso backup writes)
# ---------------------------------------------------------------------------

class _Row:
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
    def lastrowid(self) -> int | None:
        return getattr(self._c, "lastrowid", None)

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


class _TursoConn:
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

    def __enter__(self) -> "_TursoConn":
        return self

    def __exit__(self, exc_type: Any, *_: Any) -> None:
        if exc_type is None:
            self._c.commit()


def _split_sql(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


# ---------------------------------------------------------------------------
# Public connection API
# ---------------------------------------------------------------------------

def connect() -> sqlite3.Connection:
    """Primary connection — always local SQLite."""
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_local() -> sqlite3.Connection:
    """Alias for connect() — kept for backward compatibility."""
    return connect()


def _connect_turso() -> _TursoConn | None:
    creds = _turso_creds()
    if not creds:
        return None
    try:
        import libsql_experimental as libsql  # type: ignore[import]
        url, token = creds
        return _TursoConn(libsql.connect(url, auth_token=token))
    except Exception as e:
        logger.warning("Turso connect failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    # Init Turso backup schema (best-effort)
    turso = _connect_turso()
    if turso:
        try:
            turso.executescript(_TURSO_SCHEMA)
        except Exception as e:
            logger.warning("Turso schema init failed: %s", e)


def rebuild_events() -> None:
    with connect() as conn:
        conn.execute("DROP TABLE IF EXISTS events")
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

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


def sync_from_turso() -> int:
    """Pull events from Turso that are missing locally. Returns inserted count.

    Fast path: compare COUNT + MAX(filed_at). Only does a full row fetch when
    the numbers differ. Runs safely in a background thread at startup.
    """
    turso = _connect_turso()
    if not turso:
        return 0
    try:
        tc = turso.execute("SELECT COUNT(*), MAX(filed_at) FROM events").fetchone()
        turso_count, turso_latest = int(tc[0] or 0), tc[1]

        with connect() as conn:
            lc = conn.execute("SELECT COUNT(*), MAX(filed_at) FROM events").fetchone()
            local_count, local_latest = int(lc[0] or 0), lc[1]

        if turso_count <= local_count:
            logger.debug("sync_from_turso: local=%d >= turso=%d, skip", local_count, turso_count)
            return 0

        logger.info("sync_from_turso: turso=%d local=%d, syncing…", turso_count, local_count)

        # Collect local file_links for dedup
        with connect() as conn:
            local_links: set[str] = {
                str(r[0]) for r in conn.execute(
                    "SELECT file_link FROM events WHERE file_link IS NOT NULL"
                ).fetchall()
            }

        # Pull all rows from Turso and filter to missing ones
        turso_rows = turso.execute(
            "SELECT code, market, doc_type, case_status, file_link, filed_at, source_month "
            "FROM events"
        ).fetchall()

        new_rows = [
            (r["code"], r["market"], r["doc_type"], r["case_status"],
             r["file_link"], r["filed_at"], r["source_month"])
            for r in turso_rows
            if r["file_link"] and str(r["file_link"]) not in local_links
        ]

        if not new_rows:
            return 0

        with connect() as conn:
            cur = conn.executemany(
                "INSERT OR IGNORE INTO events "
                "(code, market, doc_type, case_status, file_link, filed_at, source_month) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                new_rows,
            )
            inserted = cur.rowcount

        logger.info("sync_from_turso: inserted %d rows", inserted)
        return inserted
    except Exception as e:
        logger.warning("sync_from_turso failed: %s", e)
        return 0


def _sync_events_to_turso(rows: list[tuple]) -> None:
    """Background: write newly inserted events to Turso as backup."""
    turso = _connect_turso()
    if not turso:
        return
    try:
        turso.executemany(
            "INSERT OR IGNORE INTO events "
            "(code, market, doc_type, case_status, file_link, filed_at, source_month) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        logger.info("Turso backup: synced %d events", len(rows))
    except Exception as e:
        logger.warning("Turso sync failed: %s", e)


def import_rows(rows: list[dict]) -> int:
    """Insert scraped rows into local DB, then async-sync new ones to Turso."""
    inserted = 0
    new_rows: list[tuple] = []
    with connect() as conn:
        for r in rows:
            filed_iso = roc_to_iso(r.get("filed_at", ""))
            if not filed_iso:
                continue
            source_month = filed_iso[5:7]
            params = (
                r["code"],
                r.get("market"),
                r["doc_type"],
                r.get("case_status"),
                r.get("file_link"),
                filed_iso,
                source_month,
            )
            cur = conn.execute(
                "INSERT OR IGNORE INTO events "
                "(code, market, doc_type, case_status, file_link, filed_at, source_month) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                params,
            )
            if cur.rowcount > 0:
                new_rows.append(params)
            inserted += cur.rowcount

    if new_rows and _turso_creds():
        threading.Thread(
            target=_sync_events_to_turso,
            args=(new_rows,),
            daemon=True,
        ).start()

    return inserted
