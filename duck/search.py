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
# Credential format (credgoo service 'searx' or SEARXNG_URL env): URL@USER@PASS.
SEARXNG_CRED = os.environ.get("SEARXNG_URL", "")


def _searxng_creds():
    cred = SEARXNG_CRED
    if not cred:
        try:
            from credgoo import get_api_key

            cred = get_api_key("searx") or ""
        except Exception:
            return None
    parts = cred.split("@")
    if len(parts) < 3 or not parts[0]:
        return None
    return {"url": parts[0].rstrip("/"), "auth": (parts[1], parts[2])}


def _searxng_search(query: str, max_results: int):
    """Private SearXNG JSON API. Returns list[{url, description}] or None."""
    creds = _searxng_creds()
    if not creds:
        return None
    try:
        resp = requests.get(
            f"{creds['url']}/search",
            params={"q": query, "format": "json"},
            auth=creds["auth"],
            timeout=15,
        )
        if resp.status_code != 200:
            logging.error("searxng fallback HTTP %s", resp.status_code)
            return None
        rows = resp.json().get("results", [])[:max_results]
        return [{"url": r.get("url", ""),
                 "description": r.get("content") or ""} for r in rows]
    except Exception as e:
        logging.error("searxng fallback failed: %s", e)
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

    rows = _ddgs_text(query, region=region, max_results=num_results)
    if rows is not None:
        return [{"url": r.get("href", ""),
                 "description": r.get("body", "")} for r in rows]

    # ddgs exhausted -> private SearXNG fallback (already returns rows in the
    # final url/description shape)
    fallback = _searxng_search(query, num_results)
    if fallback is not None:
        logging.info("search: served by searxng fallback")
        return fallback
    return None
