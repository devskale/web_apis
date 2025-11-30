from ddgs import DDGS
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO)


def search_news(topic, region="wt-wt", safesearch="off", timelimit="m", max_results=8, page=None, backend=None, proxy=None, verify=True):
    try:
        kwargs = {
            "query": topic,
            "region": region,
            "safesearch": safesearch,
            "timelimit": timelimit,
            "max_results": max_results,
        }
        if page is not None:
            kwargs["page"] = page
        if backend is not None:
            kwargs["backend"] = backend
        if proxy is not None:
            kwargs["proxy"] = proxy
        if verify is not None:
            kwargs["verify"] = verify
        results = DDGS().news(**kwargs)
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
    try:
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

        kwargs = {
            "region": region,
            "safesearch": safesearch,
            "timelimit": timelimit,
            "max_results": max_results,
        }
        if backend is not None:
            kwargs["backend"] = backend
        if page is not None:
            kwargs["page"] = page
        if proxy is not None:
            kwargs["proxy"] = proxy
        if verify is not None:
            kwargs["verify"] = verify

        results = DDGS().text(final_query, **kwargs)
        return results
    except Exception as e:
        logging.error(f"Error searching the web: {e}")
        return []


def search_maps(
    topic,
    place,
    region="wt-wt",
    safesearch="off",
    timelimit=None,
    max_results=20,
    page=None,
    backend=None,
    site="google.com",
    inurl="maps",
    exact=False,
    exclude_terms=None,
    proxy=None,
    verify=True,
    filetype=None,
):
    try:
        q = f"{topic} {place or ''}".strip()
        results = search_web(
            q,
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
        return results
    except Exception as e:
        logging.error(f"Error searching for maps: {e}")
        return []


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


def format_results_text(results):
    return results


def format_results_maps(results):
    return results


def format_results_translate(results):
    return [results]
