"""Run 上市稿本.py as a subprocess, stream logs, import resulting CSV."""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
import threading
from pathlib import Path

from . import db

ROOT = db.ROOT
SCRIPT = ROOT / "上市稿本.py"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_jobs: dict[int, dict] = {}
_lock = threading.Lock()


def _strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def _run(job_id: int) -> None:
    job = _jobs[job_id]
    log_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(SCRIPT)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        job["pid"] = proc.pid

        for raw in proc.stdout:  # type: ignore[union-attr]
            line = _strip_ansi(raw.rstrip("\n"))
            with _lock:
                log_lines.append(line)
                job["log"] = log_lines

        proc.wait()
        job["returncode"] = proc.returncode

        inserted = 0
        if proc.returncode == 0:
            mm = dt.datetime.now().strftime("%m")
            csv_path = ROOT / f"{mm}月data.csv"
            if csv_path.exists():
                inserted = db.import_csv(csv_path, source_month=mm)

        with _lock:
            job["status"] = "success" if proc.returncode == 0 else "failed"
            job["rows_inserted"] = inserted
            job["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")

        with db.connect() as conn:
            conn.execute(
                "UPDATE scrape_jobs SET status=?, finished_at=CURRENT_TIMESTAMP, "
                "log=?, rows_inserted=? WHERE id=?",
                (job["status"], "\n".join(log_lines), inserted, job_id),
            )
    except Exception as e:  # noqa: BLE001
        with _lock:
            job["status"] = "failed"
            job["error"] = str(e)
            job["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE scrape_jobs SET status='failed', finished_at=CURRENT_TIMESTAMP, "
                "log=? WHERE id=?",
                ("\n".join(log_lines) + f"\nERROR: {e}", job_id),
            )


def start_job() -> int:
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO scrape_jobs (status) VALUES ('running')")
        job_id = cur.lastrowid

    _jobs[job_id] = {
        "id": job_id,
        "status": "running",
        "log": [],
        "started_at": dt.datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "rows_inserted": 0,
    }

    t = threading.Thread(target=_run, args=(job_id,), daemon=True)
    t.start()
    return job_id


def get_job(job_id: int, since: int = 0) -> dict | None:
    """Return job state with log lines from `since` index onward."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT id, status, started_at, finished_at, log, rows_inserted "
                    "FROM scrape_jobs WHERE id=?",
                    (job_id,),
                ).fetchone()
            if row is None:
                return None
            log_lines = (row["log"] or "").splitlines()
            return {
                "id": row["id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "rows_inserted": row["rows_inserted"],
                "log": log_lines[since:],
                "log_total": len(log_lines),
            }
        log = job["log"]
        return {
            "id": job["id"],
            "status": job["status"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
            "rows_inserted": job["rows_inserted"],
            "log": log[since:],
            "log_total": len(log),
        }
