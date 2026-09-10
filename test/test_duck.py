"""Unit tests for the duck search wrappers (DDGS is mocked - no network)."""
from unittest import mock

from duck.ducknews import search_news, search_web, search_translate


def test_search_news_returns_results():
    with mock.patch("duck.ducknews.DDGS") as ddgs:
        ddgs.return_value.news.return_value = [
            {"title": "Hi", "url": "https://example.com", "body": "b"}]
        results = search_news("OpenAI Strawberry", max_results=3)

    assert results and results[0]["title"] == "Hi"
    _, kwargs = ddgs.return_value.news.call_args
    assert kwargs["max_results"] == 3


def test_search_news_swallows_errors():
    with mock.patch("duck.ducknews.DDGS") as ddgs:
        ddgs.return_value.news.side_effect = RuntimeError("backend down")
        assert search_news("x") == []


def test_search_web_builds_operators():
    with mock.patch("duck.ducknews.DDGS") as ddgs:
        ddgs.return_value.text.return_value = [
            {"title": "t", "href": "u", "body": "b"}]
        results = search_web("fastapi", site="github.com",
                             exact=True, exclude_terms=["tutorial", ""])

    query = ddgs.return_value.text.call_args.args[0]
    assert query == '"fastapi" site:github.com -tutorial'
    assert results and results[0]["href"] == "u"


def test_search_translate_restricts_site():
    with mock.patch("duck.ducknews.DDGS") as ddgs:
        ddgs.return_value.text.return_value = []
        search_translate("hello", "de")

    query = ddgs.return_value.text.call_args.args[0]
    assert query.endswith("site:translate.google.com")
