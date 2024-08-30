#from fastapi import FastAPI, HTTPException
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
import urllib.parse

def build_goog_search_url(query: str, num_results: int) -> str:
    """Construct the Google search URL with the given query and number of results."""
    encoded_query = urllib.parse.quote(query)
    return f"https://www.google.com/search?q={encoded_query}&num={num_results*2}"

def goog_search(query: str, num_results: int ) -> List[Dict[str, str]]:
    """Perform a Google search and return a list of URLs with descriptions."""
    search_url = build_goog_search_url(query, num_results)
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        results = []
        for g in soup.find_all('div', class_='g'):
            h3_tag = g.find('h3')
            if h3_tag:
                # Get the <a> tag preceding the <h3> tag
                a_tag = h3_tag.find_previous('a')
                if a_tag and a_tag.get('href'):
                    href = a_tag.get('href')

                    # Find the description within the search result
                    description = ""
                    description_tags = g.find_all(['span', 'div'], recursive=False)
                    for desc in description_tags:
                        if desc.get_text():
                            description += desc.get_text() + " "
                    
                    # Clean up and add to results
                    if description.strip():
                        results.append({
                            "url": href,
                            "description": description.strip()
                        })
                        if len(results) >= num_results:
                            break

        return results
    except Exception as e:
        print(f"An error occurred: {e}")
        return []