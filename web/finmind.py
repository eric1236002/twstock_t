"""FinMind REST client with multi-token rotation and quota tracking."""
from __future__ import annotations

import datetime as dt
import logging
import os
import threading
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BASE = "https://api.finmindtrade.com/api/v4"
USER_INFO_URL = "https://api.web.finmindtrade.com/v2/user_info"
HOUR_LIMIT = 600  # free tier with token


def _load_tokens() -> list[str]:
    raw = os.getenv("FINMIND_TOKENS", "") or os.getenv("FINMIND_TOKEN", "")
    return [t.strip() for t in raw.split(",") if t.strip()]


class TokenPool:
    """Round-robin token pool. On 402 from a token, mark it exhausted until next hour."""

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self._lock = threading.Lock()
        # token -> {"used": int, "exhausted_until": float|None, "hour_start": float}
        self._state: dict[str, dict] = {
            t: {"used": 0, "exhausted_until": None, "hour_start": time.time()}
            for t in tokens
        }

    def _maybe_reset_hour(self, st: dict) -> None:
        now = time.time()
        if now - st["hour_start"] >= 3600:
            st["hour_start"] = now
            st["used"] = 0
            st["exhausted_until"] = None

    def pick(self) -> str | None:
        with self._lock:
            now = time.time()
            best: tuple[int, str] | None = None
            for t in self.tokens:
                st = self._state[t]
                self._maybe_reset_hour(st)
                if st["exhausted_until"] and now < st["exhausted_until"]:
                    continue
                if best is None or st["used"] < best[0]:
                    best = (st["used"], t)
            return best[1] if best else None

    def record_use(self, token: str) -> None:
        with self._lock:
            st = self._state.get(token)
            if st:
                self._maybe_reset_hour(st)
                st["used"] += 1

    def mark_exhausted(self, token: str) -> None:
        with self._lock:
            st = self._state.get(token)
            if st:
                # exhaust until next top of hour
                now = dt.datetime.now()
                next_hour = (now.replace(minute=0, second=0, microsecond=0)
                             + dt.timedelta(hours=1))
                st["exhausted_until"] = next_hour.timestamp()

    def status(self) -> list[dict]:
        with self._lock:
            now = time.time()
            out = []
            for t in self.tokens:
                st = self._state[t]
                self._maybe_reset_hour(st)
                remaining = max(0, HOUR_LIMIT - st["used"])
                exhausted = bool(st["exhausted_until"] and now < st["exhausted_until"])
                out.append({
                    "token_suffix": t[-8:],
                    "used": st["used"],
                    "remaining": 0 if exhausted else remaining,
                    "exhausted": exhausted,
                })
            return out


_pool: TokenPool | None = None


def pool() -> TokenPool:
    global _pool
    if _pool is None:
        _pool = TokenPool(_load_tokens())
    return _pool


class FinMindError(Exception):
    pass


class QuotaExhausted(FinMindError):
    pass


def get_data(dataset: str, **params: Any) -> list[dict]:
    """GET /api/v4/data with token rotation. Returns the data list (possibly empty)."""
    p = pool()
    attempts = max(1, len(p.tokens))
    last_err: Exception | None = None

    for _ in range(attempts):
        token = p.pick()
        if token is None:
            raise QuotaExhausted("All FinMind tokens exhausted for this hour")
        headers = {"Authorization": f"Bearer {token}"}
        q = {"dataset": dataset, **{k: v for k, v in params.items() if v is not None}}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{BASE}/data", headers=headers, params=q)
            p.record_use(token)
            if resp.status_code == 402:
                logger.warning("FinMind token ...%s exhausted (402)", token[-8:])
                p.mark_exhausted(token)
                continue
            if resp.status_code == 401:
                logger.warning("FinMind token ...%s unauthorized (401)", token[-8:])
                p.mark_exhausted(token)
                continue
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") == 402:
                p.mark_exhausted(token)
                continue
            return body.get("data") or []
        except httpx.HTTPError as e:
            last_err = e
            logger.warning("FinMind HTTP error: %s", e)
            continue

    if last_err:
        raise FinMindError(f"All tokens failed: {last_err}")
    raise QuotaExhausted("All FinMind tokens exhausted")


def quota_remaining() -> dict:
    """Return aggregate quota across all tokens."""
    p = pool()
    by_token = p.status()
    total_used = sum(s["used"] for s in by_token)
    total_remaining = sum(s["remaining"] for s in by_token)
    total_limit = HOUR_LIMIT * len(p.tokens)
    return {
        "tokens": len(p.tokens),
        "used": total_used,
        "remaining": total_remaining,
        "limit": total_limit,
        "by_token": by_token,
    }
