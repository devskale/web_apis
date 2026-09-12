"""Circuit breaker for the SearXNG primary backend.

When the lubu box is down, every /duck/search request would burn up to
2×15s in SearXNG timeouts before falling through to ddgs. This breaker
opens after N consecutive failures and short-circuits straight to the
fallback for a cooldown, then half-opens (one probe request).

State lives in duck/data/searxng_breaker.json. Two gunicorn workers race
on it — that is benign (worst case: one extra probe or one request paying
the timeout while the breaker opens).
"""
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_BREAKER_PATH = os.path.join(_DATA_DIR, "searxng_breaker.json")

_FAILURES_TO_OPEN = int(os.environ.get("SEARXNG_BREAKER_THRESHOLD", "2"))
_OPEN_SECONDS = float(os.environ.get("SEARXNG_BREAKER_COOLDOWN", "300"))


def _read() -> dict:
    try:
        with open(_BREAKER_PATH, encoding="utf-8") as fh:
            state = json.load(fh)
            return {"failures": int(state.get("failures", 0)),
                    "opened_at": float(state.get("opened_at", 0))}
    except (OSError, ValueError, TypeError):
        return {"failures": 0, "opened_at": 0.0}


def _write(state: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _BREAKER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, _BREAKER_PATH)


def searxng_available() -> bool:
    """True when the breaker is closed, or half-open after the cooldown."""
    state = _read()
    if state["failures"] < _FAILURES_TO_OPEN:
        return True
    if time.time() - state["opened_at"] > _OPEN_SECONDS:
        logger.info("searxng breaker: half-open (probing)")
        return True
    return False


def record_searxng(ok: bool) -> None:
    state = _read()
    if ok:
        if state["failures"]:
            logger.info("searxng breaker: closed (recovered)")
        state = {"failures": 0, "opened_at": 0.0}
    else:
        state["failures"] += 1
        if state["failures"] >= _FAILURES_TO_OPEN:
            state["opened_at"] = time.time()
            logger.warning("searxng breaker: OPEN for %.0fs",
                           _OPEN_SECONDS)
    _write(state)
