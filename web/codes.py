"""Refresh listed + OTC company code lists from TWSE ISIN.

ISIN strMode=2 = 上市 (listed), strMode=4 = 上櫃 (OTC). We keep only the
sections that file 增資/公司債稿本 — 股票 + 創新板 (listed) / 股票 (OTC) — and
drop 認購(售)權證 / ETF / ETN / TDR / 特別股 / 受益證券. Output is written with
ASCII filenames under codes/.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CODES_DIR = ROOT / "codes"
LISTED_FILE = CODES_DIR / "listed.csv"
OTC_FILE = CODES_DIR / "otc.csv"

ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
CODE_RE = re.compile(r"^\d{4}$")  # 4-digit company codes only

# strMode → sections that are companies filing 稿本
MARKET_SECTIONS = {
    2: {"股票", "創新板"},   # 上市 listed
    4: {"股票"},             # 上櫃 OTC
}


def fetch_codes(str_mode: int) -> list[str]:
    """Return sorted unique 4-digit company codes for a strMode page."""
    sections = MARKET_SECTIONS[str_mode]
    resp = httpx.get(ISIN_URL.format(mode=str_mode), timeout=30.0)
    resp.encoding = "cp950"  # TWSE ISIN page is Big5/MS950
    sp = BeautifulSoup(resp.text, "html.parser")
    table = sp.find("table", class_="h4") or sp.find("table")

    section: str | None = None
    codes: set[str] = set()
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) == 1:  # category header row
            section = cells[0].get_text(strip=True)
            continue
        if len(cells) < 5 or section not in sections:
            continue
        code = cells[0].get_text(strip=True).split("　")[0].split()[0]
        if CODE_RE.match(code):
            codes.add(code)
    return sorted(codes)


def update_code_lists() -> dict[str, int]:
    """Write codes/listed.csv + codes/otc.csv. Returns {market: count}."""
    CODES_DIR.mkdir(exist_ok=True)
    listed = fetch_codes(2)
    otc = fetch_codes(4)
    LISTED_FILE.write_text("\n".join(listed) + "\n", encoding="utf-8")
    OTC_FILE.write_text("\n".join(otc) + "\n", encoding="utf-8")
    return {"listed": len(listed), "otc": len(otc)}


def load_codes(markets: tuple[str, ...] = ("listed", "otc")) -> list[tuple[str, str]]:
    """Read code lists, return [(code, market), ...] (union across markets)."""
    files = {"listed": LISTED_FILE, "otc": OTC_FILE}
    out: list[tuple[str, str]] = []
    for m in markets:
        path = files[m]
        if not path.exists():
            continue
        for c in path.read_text(encoding="utf-8").splitlines():
            c = c.strip()
            if c:
                out.append((c, m))
    return out


if __name__ == "__main__":
    counts = update_code_lists()
    print(f"updated codes: listed={counts['listed']}, otc={counts['otc']}")
