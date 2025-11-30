from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Depends, Security, Request, UploadFile, File
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
from w3m.w3m import fetch_with_w3m, w3m_google
from echo.echoing import echoing
from goog.goog import goog_search
from duck.ducknews import search_news, search_text, search_maps, search_translate, search_web
from lynx.lynx import lynx_url
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import io
import pdfplumber

# Setup logger with RotatingFileHandler
access_logger = logging.getLogger("accessLogger")
access_logger.setLevel(logging.INFO)
handler = RotatingFileHandler("api.log", maxBytes=4096, backupCount=1)
formatter = logging.Formatter(
    "%(asctime)s - %(client_ip)s - %(method)s - %(path)s - %(auth)s - %(params)s")
handler.setFormatter(formatter)
access_logger.addHandler(handler)

security = HTTPBearer()

load_dotenv()

# Load tokens from environment variables
tokens_str = os.getenv('TOKENS')
if not tokens_str:
    raise ValueError("TOKENS environment variable not set")

valid_tokens = {token.strip() for token in tokens_str.split(',')}
# For debugging
print(f"Loaded {len(valid_tokens)} valid tokens {valid_tokens}")


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    print(f"Received token: {token}")  # Debugging line: print the token
    if token not in valid_tokens:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


origins = [
    "*",
    # "http://jMacAir.local:5173",
    # "http://airpm.local:5173"
]

app = FastAPI(root_path="/api")
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


@app.get("/duck/news")
def get_news(topic: str, token: str = Depends(verify_token)):
    results = search_news(topic)
    if not results:
        raise HTTPException(status_code=404, detail="No news found.")
    return {"results": results}


@app.get("/duck/text")
def get_text(text: str, token: str = Depends(verify_token)):
    results = search_text(text)
    if not results:
        raise HTTPException(status_code=404, detail="No text found.")
    return {"results": results}


@app.get("/duck/search")
def get_duck_search(
    query: str,
    max_results: int = 25,
    region: str = "wt-wt",
    safesearch: str = "off",
    timelimit: Optional[str] = None,
    backend: Optional[str] = None,
    site: Optional[str] = None,
    exact: bool = False,
    exclude: Optional[str] = None,
    page: Optional[int] = None,
    proxy: Optional[str] = None,
    verify: Optional[bool] = True,
    filetype: Optional[str] = None,
    inurl: Optional[str] = None,
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


@app.get("/duck/maps")
def get_maps(topic: str, place: Optional[str] = None, token: str = Depends(verify_token)):
    results = search_maps(topic, place)
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


@app.post("/pdf/to_md")
async def pdf_to_md(file: UploadFile = File(...), token: str = Depends(verify_token)):
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail="File too large (max 10MB)")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    parts.append(text)
            markdown = "\n\n".join(parts).strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not markdown:
        raise HTTPException(status_code=422, detail="No text extracted")
    return {"markdown": markdown}


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
