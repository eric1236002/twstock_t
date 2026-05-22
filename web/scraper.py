"""上市稿本 scraper, integrated into the backend (no external script / subprocess).

Ported from the standalone 上市稿本.py: POSTs each code in 上市代碼/CODE.csv to
the TWSE doc endpoint through a residential proxy, keeps rows whose doc type is
公司債/增資 稿本, and writes MM月data.csv (UTF-8) in the repo root.
"""
from __future__ import annotations

import concurrent.futures
import csv
import datetime as dt
import logging
import os
import threading
from pathlib import Path
from typing import Callable

import httpx
import urllib3
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CODES_FILE = ROOT / "上市代碼" / "CODE.csv"
DOC_URL = "https://doc.twse.com.tw/server-java/t57sb01"
DOC_TYPES = {"各類公司債(稿本)", "增資發行(稿本)"}
MAX_WORKERS = 50

LogFn = Callable[[str], None]


def _proxy_url() -> str:
    user = os.getenv("PROXY_USERNAME")
    pw = os.getenv("PROXY_PASSWORD")
    host = os.getenv("PROXY_HOST")
    port = os.getenv("PROXY_PORT")
    return f"http://{user}:{pw}@{host}:{port}"


@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
def _fetch_code(code: str, year: int, month: int, proxy_url: str, log: LogFn) -> list[list[str]]:
    """Fetch one code; return raw matched table rows (list of cell-text lists)."""
    # verify=False is intentional — endpoint misbehaves through this proxy (see CLAUDE.md)
    with httpx.Client(proxy=proxy_url, verify=False, timeout=30.0) as client:
        payload = {
            "id": "", "key": "", "step": "1",
            "co_id": code, "year": year, "seamon": month,
            "mtype": "B", "dtype": "",
        }
        try:
            log(f"Code: {code}")
            resp = client.post(DOC_URL, data=payload)
            resp.raise_for_status()
            sp = BeautifulSoup(resp.text, "html.parser")
            rows = [tr.find_all("td") for tr in sp.find_all("tr")]
            out: list[list[str]] = []
            for cells in rows[2:]:
                if len(cells) > 5 and cells[5].text in DOC_TYPES:
                    out.append([td.text for td in cells])
            return out
        except Exception as e:  # noqa: BLE001 — reraise to trigger tenacity retry
            log(f"ERROR {code}: {e}")
            raise


def run_listed_scrape(log: LogFn) -> Path:
    """Scrape all listed codes, write MM月data.csv, return its path.

    `log` receives progress/log lines (one per call) for streaming to the UI.
    """
    proxy_url = _proxy_url()
    codes = [c for c in CODES_FILE.read_text(encoding="utf-8").splitlines() if c.strip()]

    now = dt.datetime.now()
    year = now.year - 1911            # ROC year
    month = now.month - 1             # site indexes by previous month (see CLAUDE.md)

    log(f"開始抓取 {len(codes)} 檔上市公司（year={year}, seamon={month}）")

    matched: list[list[str]] = []
    lock = threading.Lock()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_fetch_code, code, year, month, proxy_url, log): code
            for code in codes
        }
        for fut in concurrent.futures.as_completed(futures):
            try:
                rows = fut.result()
                if rows:
                    with lock:
                        matched.extend(rows)
                        for r in rows:
                            log(f"  → {r[0]} {r[5]} {r[9]}")
            except Exception as e:  # noqa: BLE001 — exhausted retries for this code
                log(f"放棄 {futures[fut]}: {e}")

    # columns 0,5,9 = code, doc_type, ROC datetime
    final = [[r[0], r[5], r[9]] for r in matched]
    out_path = ROOT / f"{now.strftime('%m')}月data.csv"
    with out_path.open("wt", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(final)

    log(f"完成：{len(final)} 筆，寫入 {out_path.name}")
    return out_path
