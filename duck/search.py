from ddgs import DDGS
import logging

logging.basicConfig(level=logging.INFO)

def search(query: str, num_results: int = 10, domain: str = 'at') -> list:
    """
    Perform a search using DuckDuckGo with domain mapping.
    Moved from w3m/w3m.py (was w3m_google).
    """
    try:
        results = []
        # DDGS doesn't support 'domain' strictly like google, but region can be used.
        # Mapping domain 'at' to region 'at-at', 'de' to 'de-de', etc.
        region = "wt-wt"
        if domain == "at":
            region = "at-at"
        elif domain == "de":
            region = "de-de"
        elif domain == "com":
            region = "us-en"
            
        ddgs_gen = DDGS().text(query, region=region, max_results=num_results)
        for r in ddgs_gen:
            results.append({
                "url": r.get("href", ""),
                "description": r.get("body", "")
            })
        return results
    except Exception as e:
        logging.error(f"An error occurred with DDGS: {e}")
        return []
