"""Background scrape jobs: run the in-process scraper, stream logs, import to DB."""
from __future__ import annotations

import datetime as dt
import threading

from . import db, scraper

_jobs: dict[int, dict] = {}
_lock = threading.Lock()


def _run(job_id: int, roc_year: int, seamon: int | None) -> None:
    job = _jobs[job_id]
    log_lines: list[str] = []

    def log(line: str) -> None:
        with _lock:
            log_lines.append(line)
            job["log"] = log_lines

    try:
        inserted = scraper.run_scrape(log, roc_year, seamon)

        with _lock:
            job["status"] = "success"
            job["rows_inserted"] = inserted
            job["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")

        with db.connect() as conn:
            conn.execute(
                "UPDATE scrape_jobs SET status='success', finished_at=CURRENT_TIMESTAMP, "
                "log=?, rows_inserted=? WHERE id=?",
                ("\n".join(log_lines), inserted, job_id),
            )
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        with _lock:
            job["status"] = "failed"
            job["error"] = str(e)
            job["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
        with db.connect() as conn:
            conn.execute(
                "UPDATE scrape_jobs SET status='failed', finished_at=CURRENT_TIMESTAMP, "
                "log=? WHERE id=?",
                ("\n".join(log_lines), job_id),
            )


def start_job(roc_year: int | None = None, seamon: int | None = None) -> int:
    """Start a scrape. Defaults to the current ROC month (ongoing use);
    pass roc_year with seamon=None for a whole-year backfill."""
    if roc_year is None:
        roc_year, seamon = scraper.current_roc_month()

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

    threading.Thread(target=_run, args=(job_id, roc_year, seamon), daemon=True).start()
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
