from ddgs import DDGS
from datetime import datetime, timezone
import logging
import os
import time

from duck.search import _searxng_search
from duck.throttle import DdgThrottleTimeout, ddg_slot

logging.basicConfig(level=logging.INFO)

# ddgs is flaky in bursts (DNS hiccups, soft blocks): retry before giving up.
# None signals a backend error; [] means the search genuinely returned nothing.
_DDGS_ATTEMPTS = 3

# Default engines. ddgs 9.16 "auto" lets one failing engine (duckduckgo
# timeout, brave/google 429, mojeek 403, wikipedia DNS-broken for wt-wt)
# dominate or kill the whole call. Probed per-engine from the amd IP
# (2026-09-12): ONLY yahoo answers reliably (~1s, bing-powered index);
# startpage parses empty, grokipedia is thin. Env: DDG_BACKENDS="yahoo"
# (comma list) or "auto"/"all".
_raw_backends = os.environ.get("DDG_BACKENDS", "yahoo").strip()
DEFAULT_BACKEND = (
    _raw_backends if _raw_backends in {"auto", "all"}
    else [b.strip() for b in _raw_backends.split(",") if b.strip()]
)

# SearXNG time_range values for ddgs timelimit letters
_SX_TIME_RANGE = {"d": "day", "w": "week", "m": "month", "y": "year"}


def _searxng_web(final_query: str, max_results: int, timelimit: str | None):
    """Primary: private SearXNG (lubu) aggregates google/brave/startpage
    from the home IP — not bot-blocked like the amd datacenter IP. Query
    operators (site:, filetype:, -term, "...") pass straight through.
    Returns ddgs-shaped rows, or None when SearXNG is unavailable.
    """
    rows = _searxng_search(
        final_query, max_results,
        time_range=_SX_TIME_RANGE.get(timelimit) if timelimit else None,
    )
    if rows is None:
        return None
    return [
        {"title": r.get("title", ""), "href": r.get("url", ""),
         "body": r.get("description", "")}
        for r in rows
    ]


def _ddgs_call(fn, **kwargs):
    last_exc = None
    for attempt in range(_DDGS_ATTEMPTS):
        try:
            with ddg_slot():
                return fn(**kwargs)
        except DdgThrottleTimeout as e:
            # Box saturated: retrying would only deepen the queue — fail fast.
            logging.error("DDGS throttle timeout (queue full): %s", e)
            return None
        except Exception as e:
            # All engines answered but found nothing — that is an empty
            # result, not a backend failure. Retrying would not change it.
            if "No results found" in str(e):
                return []
            last_exc = e
            if attempt < _DDGS_ATTEMPTS - 1:
                time.sleep(1 + attempt)
    logging.error("DDGS failed after %d attempts: %s", _DDGS_ATTEMPTS, last_exc)
    return None


def search_news(topic, region="wt-wt", safesearch="off", timelimit="m", max_results=8, page=None, backend=None, proxy=None, verify=True):
    kwargs = {
        "query": topic,
        "region": region,
        "safesearch": safesearch,
        "timelimit": timelimit,
        "max_results": max_results,
    }
    if page is not None:
        kwargs["page"] = page
    kwargs["backend"] = backend if backend is not None else DEFAULT_BACKEND
    if proxy is not None:
        kwargs["proxy"] = proxy
    if verify is not None:
        kwargs["verify"] = verify
    return _ddgs_call(DDGS().news, **kwargs)


def search_web(
    query,
    max_results=25,
    region="wt-wt",
    safesearch="off",
    timelimit=None,
    backend=None,
    site=None,
    exact=False,
    exclude_terms=None,
    page=None,
    proxy=None,
    verify=True,
    filetype=None,
    inurl=None,
):
    exclude_terms = exclude_terms or []
    terms = []
    if exact:
        terms.append(f'"{query}"')
    else:
        terms.append(query)
    if site:
        terms.append(f"site:{site}")
    if filetype:
        terms.append(f"filetype:{filetype}")
    if inurl:
        terms.append(f"inurl:{inurl}")
    for t in exclude_terms:
        if t:
            terms.append(f"-{t}")
    final_query = " ".join(terms)

    # SearXNG first (google/brave/startpage via lubu); ddgs/yahoo fallback
    sx = _searxng_web(final_query, max_results, timelimit)
    if sx is not None:
        return sx

    kwargs = {
        "region": region,
        "safesearch": safesearch,
        "timelimit": timelimit,
        "max_results": max_results,
    }
    kwargs["backend"] = backend if backend is not None else DEFAULT_BACKEND
    if page is not None:
        kwargs["page"] = page
    if proxy is not None:
        kwargs["proxy"] = proxy
    if verify is not None:
        kwargs["verify"] = verify

    # None = backend error (after retries); [] = genuinely empty result
    return _ddgs_call(DDGS().text, query=final_query, **kwargs)


def search_translate(topic, to_language):
    try:
        q = f"{topic} {to_language}"
        results = search_web(q, max_results=5, site="translate.google.com")
        return results
    except Exception as e:
        logging.error(f"Error translating: {e}")
        return []


def age_of_article(date):
    article_date = datetime.fromisoformat(date.replace("Z", "+00:00"))
    current_date = datetime.now(timezone.utc)
    age_delta = current_date - article_date
    return f"+{age_delta.days}d"


def format_results_news(results):
    for result in results:
        result['age'] = age_of_article(result['date'])
    return sorted(results, key=lambda x: x['age'])


def format_results_translate(results):
    return [results]
