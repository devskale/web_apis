from duckduckgo_search import DDGS
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO)

def search_news(topic):
    try:
        results = DDGS().news(keywords=topic, region="wt-wt", safesearch="off", timelimit="m", max_results=8)
        return results
    except Exception as e:
        logging.error(f"Error searching for news: {e}")
        return []

def search_text(topic):
    try:
        results = DDGS().text(topic, max_results=5)
        return results
    except Exception as e:
        logging.error(f"Error searching for text: {e}")
        return []

def search_maps(topic, place):
    try:
        results = DDGS().maps(topic, place=place, max_results=20)
        return results
    except Exception as e:
        logging.error(f"Error searching for maps: {e}")
        return []

def search_translate(topic, to_language):
    try:
        results = DDGS().translate(topic, to=to_language)
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

def format_results_text(results):
    return results

def format_results_maps(results):
    return results

def format_results_translate(results):
    return [results]