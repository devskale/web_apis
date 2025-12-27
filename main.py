from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from typing import Optional
from w3m.w3m import fetch_with_w3m, w3m_google
from echo.echoing import echoing
from goog.goog import goog_search
from duck.ducknews import search_news, search_text, search_maps, search_translate, search_web
from lynx.lynx import lynx_url
from fastapi.middleware.cors import CORSMiddleware
import logging
from logging.handlers import RotatingFileHandler

# Import auth and routers
from auth import verify_token
from pdf.router import router as pdf_router

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
    description="Endpoints for DuckDuckGo search, web tools, and PDF-to-Markdown conversion.",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging middleware to log each access


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    log_data = {
        "client_ip": request.client.host,
        "method": request.method,
        "path": request.url.path,
        "auth": request.headers.get("Authorization", "no-auth"),
        "params": str(request.query_params),
    }
    access_logger.info("", extra=log_data)
    return response


@app.get("/echo")
def echo(text: str = Query(default="Hello, World!", min_length=1), token: str = Depends(verify_token)):
    cleaned_text = echoing(text)
    return {"echo": cleaned_text}


@app.get("/w3m")
def w3m_fetch(url: str, token: str = Depends(verify_token)):
    try:
        content = fetch_with_w3m(url, links=False)
        return {"content": content}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/w3m_google")
def w3m_fetch(query: str, num_results: int = 10, domain: str = "at", token: str = Depends(verify_token)):
    try:
        content = w3m_google(query, num_results, domain)
        return {"content": content}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/duck/text")
def get_text(text: str, token: str = Depends(verify_token)):
    results = search_text(text)
    if not results:
        raise HTTPException(status_code=404, detail="No text found.")
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


@app.get(
    "/duck/maps",
    tags=["Duck"],
    summary="Maps-like search filtered by domain/URL",
    description=(
        "Emulates map search via text results, defaulting to Google Maps (site=google.com, inurl=maps). "
        "Supports localization, pagination, backend selection, proxy, SSL verification, and query operators."),
)
def get_maps(
    topic: str = Query(..., description="Search topic (e.g., 'apotheke')."),
    place: Optional[str] = Query(
        None, description="Place name (e.g., 'neusiedl am see')."),
    region: str = Query(
        "wt-wt", description="Localization region, e.g. 'at-at', 'de-de', 'wt-wt'."),
    safesearch: str = Query(
        "off", description="Content filter: on, moderate, off."),
    timelimit: Optional[str] = Query(
        None, description="Time range: d, w, m, y."),
    max_results: int = Query(20, description="Maximum number of results."),
    page: Optional[int] = Query(None, description="Results page number."),
    backend: Optional[str] = Query(
        None, description="Backend: auto, all, bing, duckduckgo, yahoo."),
    site: Optional[str] = Query(
        "google.com", description="Domain restriction, defaults to google.com."),
    inurl: Optional[str] = Query(
        "maps", description="URL fragment filter, defaults to 'maps'."),
    exact: bool = Query(
        False, description="Quote the query for exact phrase matching."),
    exclude: Optional[str] = Query(
        None, description="Comma-separated terms to exclude."),
    proxy: Optional[str] = Query(
        None, description="Proxy URL, e.g. socks5h://127.0.0.1:9150."),
    verify: Optional[bool] = Query(
        True, description="Verify SSL certificates."),
    filetype: Optional[str] = Query(
        None, description="Filter by file extension."),
    token: str = Depends(verify_token),
):
    exclude_terms = [t.strip() for t in exclude.split(",")] if exclude else []
    results = search_maps(
        topic,
        place,
        region=region,
        safesearch=safesearch,
        timelimit=timelimit,
        max_results=max_results,
        page=page,
        backend=backend,
        site=site,
        inurl=inurl,
        exact=exact,
        exclude_terms=exclude_terms,
        proxy=proxy,
        verify=verify,
        filetype=filetype,
    )
    if not results:
        raise HTTPException(status_code=404, detail="No maps found.")
    return {"results": results}


@app.get("/duck/translate")
def get_duck_translation(text: str, to_language: str, token: str = Depends(verify_token)):
    results = search_translate(text, to_language)
    if not results:
        raise HTTPException(status_code=404, detail="No translation found.")
    return {"results": results}


@app.get("/goog")
def get_googlesearch(query: str, num_results: int = 10, token: str = Depends(verify_token)):
    results = goog_search(query, num_results)
    if not results:
        raise HTTPException(status_code=404, detail="No results found.")
    return {"results": results}


@app.get("/lynx")
def get_lynx_url(url: str, token: str = Depends(verify_token)):
    results = lynx_url(url)
    if not results:
        raise HTTPException(status_code=404, detail="No results found.")
    return {"results": results}


# Include routers
app.include_router(pdf_router, prefix="/pdf")

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
        print(f"Electricity module found but could not be loaded: {e}")
else:
    print("Electricity module not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
