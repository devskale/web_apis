import json
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
# Credentials are resolved via credgoo service 'searx' (format URL@USER@PASS),
# persisted to data/searxng_creds.json AND mirrored into the .env
# (SEARXNG_URL=...). Re-pulled fresh when older than SEARXNG_CREDS_REFRESH_DAYS.
SEARXNG_CREDS_REFRESH_DAYS = int(os.environ.get("SEARXNG_CREDS_REFRESH_DAYS", "7"))

_sx_state_path = os.path.join(os.path.dirname(__file__), "data", "searxng_creds.json")
_sx_mem: dict = {"creds": None, "ts": 0.0}


def _parse_cred(cred: str):
    parts = (cred or "").split("@")
    if len(parts) < 3 or not parts[0]:
        return None
    return {"url": parts[0].rstrip("/"), "auth": (parts[1], parts[2])}


def _load_searxng_state():
    try:
        with open(_sx_state_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _persist_searxng_state(cred: str, ts: float) -> None:
    os.makedirs(os.path.dirname(_sx_state_path), exist_ok=True)
    tmp = _sx_state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"cred": cred, "ts": ts}, fh)
    os.replace(tmp, _sx_state_path)


def _update_env_line(cred: str) -> None:
    """Mirror SEARXNG_URL into .env so the credential survives and is visible."""
    try:
        env_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", ".env"))
        lines = []
        found = False
        if os.path.exists(env_path):
            lines = open(env_path, encoding="utf-8").read().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("SEARXNG_URL="):
                lines[i] = f"SEARXNG_URL={cred}"
                found = True
                break
        if not found:
            lines.append(f"SEARXNG_URL={cred}")
        tmp = env_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, env_path)
    except OSError as e:
        logging.error("searxng: .env update failed: %s", e)


def _searxng_creds():
    """Resolve SearXNG credentials. Order: 1h in-process cache → persisted
    state (fresh within SEARXNG_CREDS_REFRESH_DAYS) → credgoo re-pull (which
    is persisted and mirrored to .env). Stale-tolerant: if the re-pull fails,
    the last known credential keeps serving."""
    now = time.time()
    if _sx_mem["creds"] and now - _sx_mem["ts"] < 3600:
        return _sx_mem["creds"]

    state = _load_searxng_state()
    if state and now - state.get("ts", 0) < SEARXNG_CREDS_REFRESH_DAYS * 86400:
        creds = _parse_cred(state.get("cred", ""))
        if creds:
            _sx_mem.update(creds=creds, ts=now)
            return creds

    # TTL exceeded (or nothing persisted): re-pull via credgoo
    logging.info("searxng: credential TTL exceeded — re-pulling via credgoo")
    cred = ""
    try:
        from credgoo import get_api_key

        cred = get_api_key("searx") or ""
    except Exception as e:
        logging.error("searxng: credgoo re-pull failed: %s", e)
    parsed = _parse_cred(cred) if cred else None
    if parsed:
        _persist_searxng_state(cred, now)
        _update_env_line(cred)
        _sx_mem.update(creds=parsed, ts=now)
        return parsed

    # refresh failed — keep serving the stale credential rather than failing
    if state:
        creds = _parse_cred(state.get("cred", ""))
        if creds:
            _sx_mem.update(creds=creds, ts=now)
            return creds
    return None


def _searxng_search(query: str, max_results: int):
    """Private SearXNG JSON API. Returns list[{url, description}] or None.
    Also retried: the instance limiter occasionally serves HTML bursts."""
    creds = _searxng_creds()
    logging.warning("searxng search called: creds=%s",
                    "ok" if creds else "NONE")
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
            logging.warning("searxng attempt %d: HTTP %s", attempt + 1,
                            resp.status_code)
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
    logging.warning("search: searxng -> %s", len(results) if results is not None else "None")
    if results is not None:
        return results

    rows = _ddgs_text(query, region=region, max_results=num_results)
    if rows is not None:
        return [{"url": r.get("href", ""),
                 "description": r.get("body", "")} for r in rows]
    return None
