# from fastapi import FastAPI, HTTPException
from typing import List, Dict
from ddgs import DDGS


def goog_search(query: str, num_results: int) -> List[Dict[str, str]]:
    """Perform a search (using DuckDuckGo as backend) and return a list of URLs with descriptions."""
    try:
        results = []
        ddgs_gen = DDGS().text(query, max_results=num_results)
        for r in ddgs_gen:
            results.append({
                "url": r.get("href", ""),
                "description": r.get("body", "")
            })
        return results
    except Exception as e:
        print(f"An error occurred: {e}")
        return []
