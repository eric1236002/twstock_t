"""SQLite schema and connection helpers."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "twstock.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    market TEXT,                 -- 'listed' | 'otc'
    doc_type TEXT NOT NULL,      -- 資料細節說明: 各類公司債(稿本)/各類公司債/增資發行(稿本)/...
    case_status TEXT,            -- 結案類型: 尚未結案 / 生效 / ...
    file_link TEXT,              -- 電子檔案: e.g. 202603_2330_B021.pdf
    filed_at DATETIME NOT NULL,  -- 上傳日期
    source_month TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, file_link)
);
CREATE INDEX IF NOT EXISTS idx_events_code ON events(code);
CREATE INDEX IF NOT EXISTS idx_events_filed_at ON events(filed_at);

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

CREATE TABLE IF NOT EXISTS scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    status TEXT NOT NULL,
    log TEXT,
    rows_inserted INTEGER DEFAULT 0
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def rebuild_events() -> None:
    """DROP + CREATE the events table (used when the schema changes / backfilling)."""
    with connect() as conn:
        conn.execute("DROP TABLE IF EXISTS events")
        conn.executescript(SCHEMA)


def roc_to_iso(roc: str) -> str | None:
    """Convert '115/04/23 11:04:40' (ROC year) → '2026-04-23 11:04:40'."""
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
    """Insert scraped event rows directly. Each row dict has keys:
    code, market, doc_type, case_status, file_link, filed_at (ROC datetime string).
    Returns rows newly inserted (dedup by UNIQUE(code, file_link))."""
    inserted = 0
    with connect() as conn:
        for r in rows:
            filed_iso = roc_to_iso(r.get("filed_at", ""))
            if not filed_iso:
                continue
            source_month = filed_iso[5:7]  # MM
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
