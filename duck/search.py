import os
import time

from ddgs import DDGS
import logging
import requests

logging.basicConfig(level=logging.INFO)

# ddgs is flaky in bursts (DNS hiccups, soft blocks): retry before giving up.
# None signals a backend error; [] means the search genuinely returned nothing.
_DDGS_ATTEMPTS = 3

# Fallback when ddgs fails entirely: the private SearXNG instance.
# Resolved via credgoo service 'searx' (format URL@USER@PASS); the resolved
# credential is kept for SEARXNG_CREDS_REFRESH_DAYS, then re-pulled fresh.
# SEARXNG_URL env overrides credgoo entirely if set.
SEARXNG_CRED = os.environ.get("SEARXNG_URL", "")
SEARXNG_CREDS_REFRESH_DAYS = int(os.environ.get("SEARXNG_CREDS_REFRESH_DAYS", "7"))

_sx_cred_cache: dict = {"creds": None, "ts": 0.0}


def _searxng_creds():
    """Resolve SearXNG credentials via credgoo, re-pulled every N days.
    Stale-tolerant: if a re-pull fails, the last known creds keep serving."""
    now = time.time()
    cached = _sx_cred_cache["creds"]
    if cached and now - _sx_cred_cache["ts"] < SEARXNG_CREDS_REFRESH_DAYS * 86400:
        return cached
    cred = SEARXNG_CRED
    if not cred:
        try:
            from credgoo import get_api_key

            cred = get_api_key("searx") or ""
        except Exception as e:
            logging.error("searxng: credgoo resolution failed: %s", e)
    parts = (cred or "").split("@")
    if len(parts) < 3 or not parts[0]:
        logging.error("searxng: credential has unexpected format (len %d parts)",
                      len(parts))
        return cached  # keep serving the stale creds rather than failing
    creds = {"url": parts[0].rstrip("/"), "auth": (parts[1], parts[2])}
    _sx_cred_cache["creds"] = creds
    _sx_cred_cache["ts"] = now
    return creds


def _searxng_search(query: str, max_results: int):
    """Private SearXNG JSON API. Returns list[{url, description}] or None.
    Also retried: the instance limiter occasionally serves HTML bursts."""
    creds = _searxng_creds()
    if not creds:
        return None
    last_err = "no attempt"
    for attempt in range(2):
        try:
            resp = requests.get(
                f"{creds['url']}/search",
                params={"q": query, "format": "json"},
                auth=creds["auth"],
                timeout=15,
            )
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}"
            else:
                rows = resp.json().get("results", [])[:max_results]
                return [{"url": r.get("url", ""),
                         "description": r.get("content") or ""} for r in rows]
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt == 0:
            time.sleep(1)
    logging.error("searxng fallback failed: %s", last_err)
    return None


def _ddgs_text(query: str, **kwargs):
    last_exc = None
    for attempt in range(_DDGS_ATTEMPTS):
        try:
            return list(DDGS().text(query, **kwargs))
        except Exception as e:
            last_exc = e
            if attempt < _DDGS_ATTEMPTS - 1:
                time.sleep(1 + attempt)
    logging.error("DDGS failed after %d attempts: %s", _DDGS_ATTEMPTS, last_exc)
    return None


def search(query: str, num_results: int = 10, domain: str = 'at') -> list | None:
    """
    Perform a search using DuckDuckGo with domain mapping.
    Moved from w3m/w3m.py (was w3m_google).
    Returns None on backend failure (vs [] for a genuinely empty result).
    """
    region = "wt-wt"
    if domain == "at":
        region = "at-at"
    elif domain == "de":
        region = "de-de"
    elif domain == "com":
        region = "us-en"

    # SearXNG first: it aggregates from the lubu box (not bot-blocked like the
    # amd datacenter IP — google/brave/mojeek answer 429/403/CAPTCHA here).
    # DDG remains the fallback for the rare case SearXNG fails.
    results = _searxng_search(query, num_results)
    if results is not None:
        return results

    rows = _ddgs_text(query, region=region, max_results=num_results)
    if rows is not None:
        return [{"url": r.get("href", ""),
                 "description": r.get("body", "")} for r in rows]
    return None
