"""SQLite schema and connection helpers."""
from __future__ import annotations

import csv
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
    doc_type TEXT NOT NULL,
    filed_at DATETIME NOT NULL,
    source_month TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, doc_type, filed_at)
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


def import_csv(csv_path: Path, source_month: str | None = None) -> int:
    """Import a scraper CSV (code, doc_type, ROC datetime). Returns rows inserted."""
    if source_month is None:
        m = re.match(r"(\d{2})月", csv_path.name)
        source_month = m.group(1) if m else None
    inserted = 0
    with connect() as conn, csv_path.open("r", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            code, doc_type, roc = row[0].strip(), row[1].strip(), row[2].strip()
            filed_at = roc_to_iso(roc)
            if not filed_at:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO events (code, doc_type, filed_at, source_month) "
                "VALUES (?, ?, ?, ?)",
                (code, doc_type, filed_at, source_month),
            )
            inserted += cur.rowcount
    return inserted


def import_all_csvs() -> int:
    """Bootstrap: import every MM月data.csv in the repo root."""
    total = 0
    for p in sorted(ROOT.glob("*月data.csv")):
        total += import_csv(p)
    return total
