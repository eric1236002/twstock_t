"""Unified 上市+上櫃 稿本 scraper, integrated into the backend.

Both markets use the same TWSE doc endpoint (t57sb01, mtype=B); the only
difference is which co_ids we feed. Sends one request per code:
  - seamon="" + year=ROC  → the whole year's filings (used for backfill)
  - seamon=N              → just month N (used for the ongoing monthly scrape)

Keeps rows whose 資料細節說明 contains 公司債 / 增資 (both the (稿本) draft and the
生效 effective versions) and records 結案類型 / 電子檔案 / 上傳日期. Writes straight
to the events table via db.import_rows — no intermediate CSV.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
import os
import threading
from typing import Callable

import httpx
import urllib3
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed

from . import codes as codes_mod
from . import db

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

logger = logging.getLogger(__name__)

DOC_URL = "https://doc.twse.com.tw/server-java/t57sb01"
MAX_WORKERS = 50
LogFn = Callable[[str], None]

# 資料細節說明 keywords we keep (covers (稿本) drafts and 生效 effective rows)
KEEP_KEYWORDS = ("公司債", "增資")


def _proxy_url() -> str:
    return (
        f"http://{os.getenv('PROXY_USERNAME')}:{os.getenv('PROXY_PASSWORD')}"
        f"@{os.getenv('PROXY_HOST')}:{os.getenv('PROXY_PORT')}"
    )


def current_roc_month() -> tuple[int, int]:
    now = dt.datetime.now()
    return now.year - 1911, now.month


@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
def _fetch_code(code: str, market: str, year: int, seamon: int | str, proxy_url: str) -> list[dict]:
    """Fetch one code for (year, seamon); return matched event dicts.

    seamon="" → whole year; seamon=N → that month.
    """
    # verify=False is intentional — endpoint misbehaves through this proxy (see CLAUDE.md)
    with httpx.Client(proxy=proxy_url, verify=False, timeout=30.0) as client:
        payload = {
            "id": "", "key": "", "step": "1",
            "co_id": code, "year": year, "seamon": seamon,
            "mtype": "B", "dtype": "",
        }
        resp = client.post(DOC_URL, data=payload)
        resp.raise_for_status()
        text = resp.text
        # 區分三種回應：成功頁一定有表頭「資料細節」；真的沒資料會顯示
        # 「查無所需資料」；兩者皆無 = 被限流／錯誤頁（HTTP 200 但無內容），
        # 視為軟失敗丟例外讓 tenacity 重試（否則該檔會被靜默漏抓）。
        if "資料細節" not in text:
            if "查無所需資料" in text:
                return []
            raise RuntimeError(f"軟失敗（無表頭，len={len(text)}）")
        sp = BeautifulSoup(text, "html.parser")
        out: list[dict] = []
        for tr in sp.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 10:
                continue
            detail = cells[5].get_text(strip=True)  # 資料細節說明
            if not any(k in detail for k in KEEP_KEYWORDS):
                continue
            if detail.startswith("英文版"):  # skip English-version duplicates
                continue
            out.append({
                "code": code,
                "market": market,
                "doc_type": detail,
                "case_status": cells[3].get_text(strip=True),  # 結案類型
                "file_link": cells[7].get_text(strip=True),    # 電子檔案
                "filed_at": cells[9].get_text(strip=True),     # 上傳日期
            })
        return out


def run_scrape(
    log: LogFn,
    roc_year: int,
    seamon: int | None = None,
    markets: tuple[str, ...] = ("listed", "otc"),
) -> int:
    """Scrape company filings and write them straight into the events table.

    roc_year : ROC year (e.g. 115).
    seamon   : None → whole year; int → that single month.
    Returns the number of newly inserted event rows.
    """
    proxy_url = _proxy_url()
    code_list = codes_mod.load_codes(markets)
    if not code_list:
        log("找不到代碼清單（請先執行 web.codes 更新名單）")
        return 0

    seamon_param: int | str = "" if seamon is None else seamon
    span = "整年" if seamon is None else f"{seamon} 月"
    log(f"開始抓取 {len(code_list)} 檔（{'+'.join(markets)}）· {roc_year} 年 {span} = {len(code_list)} 次請求")

    matched: list[dict] = []
    lock = threading.Lock()
    done = 0
    total = len(code_list)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_fetch_code, code, market, roc_year, seamon_param, proxy_url): (code, market)
            for code, market in code_list
        }
        for fut in concurrent.futures.as_completed(futures):
            code, market = futures[fut]
            try:
                rows = fut.result()
                if rows:
                    with lock:
                        matched.extend(rows)
                        for r in rows:
                            log(f"  → {r['code']} {r['doc_type']} [{r['case_status']}] {r['filed_at']}")
            except Exception as e:  # noqa: BLE001 — exhausted retries for this code
                log(f"放棄 {code} ({market}): {e}")
            finally:
                with lock:
                    done += 1
                    if done % 200 == 0 or done == total:
                        log(f"進度 {done}/{total}")

    inserted = db.import_rows(matched)
    log(f"完成：抓到 {len(matched)} 筆，新增 {inserted} 筆進資料庫")
    return inserted
