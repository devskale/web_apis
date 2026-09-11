from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from typing import Optional
from w3m.w3m import fetch_with_w3m
from echo.echoing import echoing
from duck.ducknews import (
    search_news,
    search_web,
    search_translate,
)
from duck.search import search as duck_search_domain
from lynx.lynx import lynx_url
from fastapi.middleware.cors import CORSMiddleware
import logging
from logging.handlers import RotatingFileHandler
# --- Simple in-memory rate limiter for /firmenbuch ---
from collections import defaultdict
from urllib.parse import urlparse
from fastapi.responses import JSONResponse, RedirectResponse
import hashlib
import time


def _mask_auth(header: str | None) -> str:
    """Return a log-safe representation of an Authorization header.

    Never writes the secret: a ``Bearer <token>`` header becomes
    ``Bearer <sha256[:8]>`` so the credential itself is unrecoverable,
    while the short hash still lets you tell which token was used across
    log lines. Non-Bearer schemes are reduced to their scheme name."""
    if not header:
        return "no-auth"
    parts = header.split(" ", 1)
    if len(parts) == 2:
        scheme, credential = parts[0], parts[1]
        digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()[:8]
        return f"{scheme} {digest}"
    return parts[0]

_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 30  # requests per window, per worker process
_RATE_WINDOW = 60  # seconds
_last_prune = 0.0


def _rate_key(request: Request) -> str:
    """One bucket per token; unauthenticated requests get a per-IP bucket so
    they can't exhaust a single shared 'anonymous' bucket."""
    auth = request.headers.get("Authorization")
    if auth:
        # Hash so raw credentials never sit in the store.
        return "tok:" + hashlib.sha256(auth.encode("utf-8")).hexdigest()
    client = request.client.host if request.client else "unknown"
    return "ip:" + client


def _check_rate_limit(key: str) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    now = time.time()
    recent = [t for t in _rate_store[key] if now - t < _RATE_WINDOW]
    if len(recent) >= _RATE_LIMIT:
        _rate_store[key] = recent
        return False
    recent.append(now)
    _rate_store[key] = recent
    return True


def _prune_rate_store() -> None:
    """Drop keys whose newest hit is older than the window, so the store can't
    grow without bound over time (matters on a low-RAM box). Runs at most once
    per window - timestamps are appended in order, so ts[-1] is the newest."""
    global _last_prune
    now = time.time()
    if now - _last_prune < _RATE_WINDOW:
        return
    _last_prune = now
    stale = [k for k, ts in _rate_store.items()
             if not ts or now - ts[-1] >= _RATE_WINDOW]
    for k in stale:
        del _rate_store[k]


def _validate_url(url: str) -> None:
    """Reject anything that isn't a plain http(s) URL, so the text browsers
    can't be pointed at file:// or other internal schemes."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=400, detail="Only http(s) URLs are supported.")


# Import auth and routers
from auth import verify_token
from pdf.router import router as pdf_router
from itoa.router import router as itoa_router

# Setup logger with RotatingFileHandler
access_logger = logging.getLogger("accessLogger")
access_logger.setLevel(logging.INFO)
handler = RotatingFileHandler("api.log", maxBytes=4096, backupCount=1)
formatter = logging.Formatter(
    "%(asctime)s - %(client_ip)s - %(method)s - %(path)s - %(auth)s - %(params)s")
handler.setFormatter(formatter)
access_logger.addHandler(handler)

origins = [
    "*",
    # "http://jMacAir.local:5173",
    # "http://airpm.local:5173"
]

app = FastAPI(
    root_path="/api",
    title="Web APIs",
    description="Endpoints for DuckDuckGo search, web tools, PDF/image conversion, and Austrian company data.",
    version="1.3.0",
)

app.include_router(pdf_router, prefix="/pdf", tags=["PDF"])
app.include_router(itoa_router, prefix="/itoa", tags=["itoa"], dependencies=[Depends(verify_token)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging middleware to log each access


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Rate limit check for firmenbuch endpoints
    limited = False
    if "/firmenbuch/" in request.url.path:
        limited = not _check_rate_limit(_rate_key(request))
    if limited:
        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Max 30 requests per minute per token."},
            headers={"Retry-After": "60"}
        )
    else:
        response = await call_next(request)
    # Periodically prune stale keys so the in-memory store can't leak.
    _prune_rate_store()
    log_data = {
        "client_ip": request.client.host,
        "method": request.method,
        "path": request.url.path,
        "auth": _mask_auth(request.headers.get("Authorization")),
        "params": str(request.query_params),
    }
    access_logger.info("", extra=log_data)
    return response


@app.get("/", include_in_schema=False)
def root(request: Request):
    """Browsers land on the Swagger UI; API clients get the JSON help."""
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(str(request.url).rstrip("/") + "/docs")
    return help_(request)


@app.get("/help", include_in_schema=False)
def help_(request: Request):
    """Agent-friendly discovery endpoint: how to authenticate, where the
    machine-readable spec lives, what the endpoint groups are."""
    # Behind nginx the worker doesn't honor proxy headers for base_url, so
    # reconstruct it explicitly (public scheme + host + root_path prefix).
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    base = f"{proto}://{host}{request.scope.get('root_path', '')}"
    return {
        "service": "Web APIs",
        "version": app.version,
        "how_to_use": {
            "auth": "Send 'Authorization: Bearer <token>' on every endpoint. "
                    "401 without/invalid token; tokens are configured server-side (TOKENS).",
            "get_a_token": "In the skale environment: `credgoo FETCH_URL_BEARER` "
                           "returns a valid token (or ask the operator for a TOKENS entry).",
            "base_url": base,
            "machine_readable_spec": base + "/openapi.json",
            "human_docs": base + "/docs",
            "example": f"curl -H 'Authorization: Bearer <token>' '{base}/echo?text=ping'",
        },
        "async_jobs": {
            "pattern": "POST /pdf/to_md?method=llamaparse&wait=false returns 202 with "
                       "{job_id, poll}. Poll GET <poll> (same Bearer auth) until "
                       "status is done|failed. Hard deadline 20 min per job.",
            "when": "llamaparse docs beyond ~40 pages are forced async automatically "
                    "(the 202 body says auto_async: true).",
            "share": "transfer=throway uploads the result to skale.dev/throway "
                     "(4h TTL) and returns markdown_url instead of the full text.",
        },
        "rate_limits": {
            "/firmenbuch/*": "30 requests/minute per token, then 429 + Retry-After",
            "pdf_jobs": "1 concurrent llamaparse conversion, max 10 jobs",
        },
        "errors": {
            "401": "missing/invalid Bearer token — see how_to_use.get_a_token",
            "422": "input parsed but yielded nothing (e.g. scan without OCR — "
                   "use method=llamaparse)",
            "429": "rate limit or quota — honor Retry-After",
            "502/504": "upstream conversion failed/timed out — retry or use wait=false",
        },
        "endpoint_groups": {
            "/echo": "health check, echoes sanitized input",
            "/fetch_url": "fetch a URL as text via w3m or lynx (http(s) only)",
            "/lynx": "fetch a URL via lynx",
            "/w3m_google": "web search (DuckDuckGo-backed, region by domain)",
            "/duck/news": "news search with region/timelimit filters",
            "/duck/search": "web search with site:/filetype:/inurl: operators",
            "/duck/translate": "translation-link search",
            "/pdf/to_md": "POST PDF -> Markdown (pdfplumber local default; "
                          "method=llamaparse for scans/OCR, tier + language params)",
            "/itoa/convert": "POST image -> ASCII art (width 1-500, modes)",
            "/firmenbuch/*": "Austrian company register: search, lookup, merged record, "
                             "ONACE, HVD extract, crawl cache (30 req/min rate limit)",
            "/electricity/*": "Austrian electricity tariffs and spot prices "
                              "(own Bearer token, not the global TOKENS)",
        },
    }


@app.get("/echo")
def echo(text: str = Query(default="Hello, World!", min_length=1), token: str = Depends(verify_token)):
    cleaned_text = echoing(text)
    return {"echo": cleaned_text}


@app.get("/fetch_url")
def fetch_url(
    url: str,
    tool: str = Query(
        "w3m", description="Tool to use: w3m (default) or lynx."),
    token: str = Depends(verify_token)
):
    _validate_url(url)
    try:
        if tool == "w3m":
            content = fetch_with_w3m(url, links=False)
            return {"content": content}
        elif tool == "lynx":
            content = lynx_url(url)
            if not content:
                raise HTTPException(
                    status_code=404, detail="No content found.")
            return {"content": content}
        else:
            raise HTTPException(
                status_code=400, detail="Invalid tool. Use 'w3m' or 'lynx'.")
    except RuntimeError as e:
        # Log the real cause server-side; don't echo internal error text.
        logging.error("/fetch_url failed for %s: %s", url, e)
        raise HTTPException(
            status_code=502, detail="Upstream fetch failed.")


@app.get("/lynx")
def lynx_fetch(url: str, token: str = Depends(verify_token)):
    _validate_url(url)
    try:
        content = lynx_url(url)
    except RuntimeError as e:
        logging.error("/lynx failed for %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Upstream fetch failed.")
    if not content:
        raise HTTPException(status_code=404, detail="No content found.")
    return {"content": content}


@app.get("/w3m_google")
def w3m_fetch(query: str, num_results: int = 10, domain: str = "at", token: str = Depends(verify_token)):
    try:
        content = duck_search_domain(query, num_results, domain)
        return {"content": content}
    except RuntimeError as e:
        logging.error("/w3m_google failed for %r: %s", query, e)
        raise HTTPException(status_code=502, detail="Search failed.")


@app.get(
    "/duck/news",
    tags=["Duck"],
    summary="DuckDuckGo news search",
    description=(
        "Search for news articles with localization and filtering parameters. "
        "Supports region, safesearch, timelimit, pagination, backend selection, proxy, and SSL verification."),
)
def get_news(
    topic: str = Query(..., description="News search topic."),
    region: str = Query(
        "wt-wt", description="Localization region, e.g. 'at-at', 'de-de', 'wt-wt'."),
    safesearch: str = Query(
        "off", description="Content filter: on, moderate, off."),
    timelimit: Optional[str] = Query(
        "m", description="Time range: d, w, m, y."),
    max_results: int = Query(8, description="Maximum number of news results."),
    page: Optional[int] = Query(None, description="Results page number."),
    backend: Optional[str] = Query(
        None, description="Backend: auto, all, bing, duckduckgo, yahoo."),
    proxy: Optional[str] = Query(
        None, description="Proxy URL, e.g. socks5h://127.0.0.1:9150."),
    verify: Optional[bool] = Query(
        True, description="Verify SSL certificates for requests."),
    token: str = Depends(verify_token),
):
    results = search_news(
        topic,
        region=region,
        safesearch=safesearch,
        timelimit=timelimit,
        max_results=max_results,
        page=page,
        backend=backend,
        proxy=proxy,
        verify=verify,
    )
    if not results:
        raise HTTPException(status_code=404, detail="No news found.")
    return {"results": results}


@app.get(
    "/duck/search",
    tags=["Duck"],
    summary="DuckDuckGo text search with advanced filters",
    description=(
        "Perform a DuckDuckGo text search with rich filters. Supports operators such as "
        "`site:<domain>`, `filetype:<ext>`, `inurl:<fragment>`, and exclusion via `exclude` list. "
        "Set `exact=true` to quote the query for exact phrase matching. You can also tune `region`, "
        "`safesearch`, `timelimit`, choose a search `backend`, paginate via `page`, and route through a `proxy`."
    ),
)
def get_duck_search(
    query: str = Query(
        ..., description="Search query. Operators supported: site:, filetype:, inurl:."),
    max_results: int = Query(
        25, description="Maximum number of results to return."),
    region: str = Query(
        "wt-wt", description="Localization region, e.g. 'at-at', 'de-de', 'wt-wt'."),
    safesearch: str = Query(
        "off", description="Content filter: on, moderate, off."),
    timelimit: Optional[str] = Query(
        None, description="Time range: d (day), w (week), m (month), y (year)."),
    backend: Optional[str] = Query(
        None,
        description=(
            "Search backend: auto, all, bing, brave, duckduckgo, google, mojeek, yandex, yahoo, wikipedia."),
    ),
    site: Optional[str] = Query(
        None, description="Restrict results to a specific domain (site:<domain>)."),
    exact: bool = Query(
        False, description="Quote the query for exact phrase matching."),
    exclude: Optional[str] = Query(
        None, description="Comma-separated terms to exclude (each becomes '-term')."),
    page: Optional[int] = Query(
        None, description="Results page number (pagination)."),
    proxy: Optional[str] = Query(
        None, description="Proxy URL, e.g. socks5h://127.0.0.1:9150."),
    verify: Optional[bool] = Query(
        True, description="Verify SSL certificates for requests."),
    filetype: Optional[str] = Query(
        None, description="Filter by file extension (filetype:<ext>)."),
    inurl: Optional[str] = Query(
        None, description="Filter by URL substring (inurl:<fragment>)."),
    token: str = Depends(verify_token),
):
    exclude_terms = [t.strip() for t in exclude.split(",")] if exclude else []
    results = search_web(
        query,
        max_results=max_results,
        region=region,
        safesearch=safesearch,
        timelimit=timelimit,
        backend=backend,
        site=site,
        exact=exact,
        exclude_terms=exclude_terms,
        page=page,
        proxy=proxy,
        verify=verify,
        filetype=filetype,
        inurl=inurl,
    )
    if not results:
        raise HTTPException(status_code=404, detail="No results found.")
    return {"results": results}


@app.get("/duck/translate")
def get_duck_translation(text: str, to_language: str, token: str = Depends(verify_token)):
    results = search_translate(text, to_language)
    if not results:
        raise HTTPException(status_code=404, detail="No translation found.")
    return {"results": results}


# Check for firmenbuch module before importing
firmenbuch_path = Path(__file__).parent / 'firmenbuch'
if firmenbuch_path.exists():
    try:
        import firmenbuch.router as firmenbuch
        from firmenbuch.router import router as firmenbuch_router
        firmenbuch.register_exception_handler(app)
        app.include_router(firmenbuch_router, prefix="/firmenbuch", tags=["Firmenbuch"], dependencies=[Depends(verify_token)])
        print("Firmenbuch module loaded successfully")
    except ImportError as e:
        logging.error("Firmenbuch module found but could not be loaded: %s", e, exc_info=True)
else:
    print("Firmenbuch module not found")

# Check for electricity module before importing
electricity_path = Path(__file__).parent / 'electricity'
if electricity_path.exists():
    try:
        from electricity.api.v1.router import router as electricity_router
        app.include_router(
            electricity_router,
            prefix="/electricity",
            dependencies=[Depends(verify_token)]
        )
        print("Electricity module loaded successfully")
    except ImportError as e:
        logging.error("Electricity module found but could not be loaded: %s", e, exc_info=True)
else:
    print("Electricity module not found")

if __name__ == "__main__":
    import uvicorn
    # Dev convenience only (production runs gunicorn behind nginx); bind to
    # localhost so a stray dev run isn't reachable from the network.
    uvicorn.run(app, host="127.0.0.1", port=8001)
