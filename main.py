from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
from w3m.w3m import fetch_with_w3m, w3m_google
from echo.echoing import echoing
from goog.goog import goog_search
from duck.ducknews import search_news, search_text, search_maps, search_translate
from lynx.lynx import lynx_url
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv


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
    if credentials.credentials not in valid_tokens:
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


# Check for electricity module before importing
electricity_path = Path(__file__).parent / 'electricity'
if electricity_path.exists():
    try:
        from electricity.api.v1.router import router as electricity_router
        app.include_router(
            electricity_router,
            prefix="/electricity",
#            dependencies=[Depends(verify_token)]
        )
        print("Electricity module loaded successfully")
    except ImportError as e:
        print(f"Electricity module found but could not be loaded: {e}")
else:
    print("Electricity module not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
