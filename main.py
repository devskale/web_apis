from fastapi import FastAPI, HTTPException, Query
from typing import Optional
from w3m.w3m import fetch_with_w3m
from echo.echoing import echoing
from duck.ducknews import search_news, search_text, search_maps, search_translate

app = FastAPI()

@app.get("/echo")
def echo(text: str = Query(default="Hello, World!", min_length=1)):
    cleaned_text = echoing(text)
    return {"echo": cleaned_text}

@app.get("/w3m")
def w3m_fetch(url: str):
    try:
        content = fetch_with_w3m(url)
        return {"content": content}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# DuckDuckGo Search Routes
@app.get("/duck/news")
def get_news(topic: str):
    results = search_news(topic)
    if not results:
        raise HTTPException(status_code=404, detail="No news found.")
    return {"results": results}

@app.get("/duck/text")
def get_text(topic: str):
    results = search_text(topic)
    if not results:
        raise HTTPException(status_code=404, detail="No text found.")
    return {"results": results}

@app.get("/duck/maps")
def get_maps(topic: str, place: Optional[str] = None):
    results = search_maps(topic, place)
    if not results:
        raise HTTPException(status_code=404, detail="No maps found.")
    return {"results": results}

@app.get("/duck/translate")
def get_translation(topic: str, to_language: str):
    results = search_translate(topic, to_language)
    if not results:
        raise HTTPException(status_code=404, detail="No translation found.")
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)