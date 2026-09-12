import time

from ddgs import DDGS
import logging

logging.basicConfig(level=logging.INFO)

# ddgs is flaky in bursts (DNS hiccups, soft blocks): retry before giving up.
# None signals a backend error; [] means the search genuinely returned nothing.
_DDGS_ATTEMPTS = 3


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
    if rows is None:
        return None
    results = []
    for r in rows:
        results.append({
            "url": r.get("href", ""),
            "description": r.get("body", "")
        })
    return results
