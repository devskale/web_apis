"""Unit tests for the duck search wrappers (DDGS is mocked - no network)."""
import os

import pytest
from unittest import mock

from duck.ducknews import search_news, search_web, search_translate


@pytest.fixture(autouse=True)
def _isolated_cache_and_breaker(tmp_path, monkeypatch):
    """Point cache + breaker state at a temp dir so tests never share
    results and never pollute the real duck/data/ state."""
    monkeypatch.setattr("duck.cache._CACHE_DIR", str(tmp_path / "qc"))
    monkeypatch.setattr("duck.router._BREAKER_PATH", str(tmp_path / "br.json"))


def test_search_news_returns_results():
    with mock.patch("duck.ducknews.DDGS") as ddgs:
        ddgs.return_value.news.return_value = [
            {"title": "Hi", "url": "https://example.com", "body": "b"}]
        results = search_news("OpenAI Strawberry", max_results=3)

    assert results and results[0]["title"] == "Hi"
    _, kwargs = ddgs.return_value.news.call_args
    assert kwargs["max_results"] == 3


def test_search_news_retries_then_returns_results():
    responses = [RuntimeError("dns hiccup"), RuntimeError("soft block"),
                 [{"title": "ok"}]]

    def flaky(**kw):
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews.time.sleep"):
        ddgs.return_value.news.side_effect = flaky
        results = search_news("x")
    assert results == [{"title": "ok"}]


def test_search_news_returns_none_after_exhausted_retries():
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews.time.sleep"):
        ddgs.return_value.news.side_effect = RuntimeError("down")
        assert search_news("x") is None


def test_search_web_builds_operators():
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews._searxng_search", return_value=None):
        ddgs.return_value.text.return_value = [
            {"title": "t", "href": "u", "body": "b"}]
        results = search_web("fastapi", site="github.com",
                             exact=True, exclude_terms=["tutorial", ""])

    query = ddgs.return_value.text.call_args.kwargs["query"]
    assert query == '"fastapi" site:github.com -tutorial'
    assert results and results[0]["href"] == "u"


def test_search_translate_restricts_site():
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews._searxng_search", return_value=None):
        ddgs.return_value.text.return_value = []
        search_translate("hello", "de")

    query = ddgs.return_value.text.call_args.kwargs["query"]
    assert query.endswith("site:translate.google.com")


def test_search_web_primary_ddgs_default():
    # Default chain: ddgs first — searxng (lubu) is never touched.
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews._searxng_search") as sx:
        ddgs.return_value.text.return_value = [
            {"title": "t", "href": "u", "body": "b"}]
        results = search_web("query")
    assert results[0]["href"] == "u"
    sx.assert_not_called()


def test_search_web_primary_searxng_when_configured(monkeypatch):
    monkeypatch.setattr("duck.ducknews._PRIMARY", "searxng")
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews._searxng_search") as sx:
        sx.return_value = [{"title": "T", "url": "https://sx", "description": "d"}]
        results = search_web("query")
    assert results == [{"title": "T", "href": "https://sx", "body": "d"}]
    ddgs.return_value.text.assert_not_called()


def test_search_web_searxng_fallback_when_ddgs_fails():
    # ddgs returns None (backend error after retries) -> searxng serves.
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews._searxng_search") as sx, \
            mock.patch("duck.ducknews.time.sleep"):
        ddgs.return_value.text.return_value = None
        ddgs.return_value.text.side_effect = RuntimeError("yahoo EOF")
        sx.return_value = [{"title": "T", "url": "https://sx", "description": "d"}]
        results = search_web("query")
    assert results[0]["href"] == "https://sx"


def test_search_web_empty_ddgs_rechecked_on_searxng():
    # [] from the single-engine primary is not final — searxng's
    # aggregated verdict (rows) wins.
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews._searxng_search") as sx:
        ddgs.return_value.text.return_value = []
        sx.return_value = [{"title": "T", "url": "https://sx", "description": "d"}]
        results = search_web("gibberish query")
    assert results[0]["href"] == "https://sx"


def test_search_web_cache_prevents_second_backend_call():
    with mock.patch("duck.ducknews.DDGS") as ddgs, \
            mock.patch("duck.ducknews._searxng_search"):
        ddgs.return_value.text.return_value = [
            {"title": "t", "href": "u", "body": "b"}]
        first = search_web("cached query")
        second = search_web("cached query")
    assert first == second
    assert ddgs.return_value.text.call_count == 1


def test_searxng_primary_and_ddg_fallback():
    from duck import search as duck_search_mod

    # searxng serves -> ddgs never called
    with mock.patch("duck.search.DDGS") as ddgs, \
            mock.patch("duck.search.time.sleep"), \
            mock.patch.object(duck_search_mod, "_searxng_creds",
                              lambda: {"url": "https://sx.test", "auth": ("u", "p")}), \
            mock.patch.object(duck_search_mod.requests, "get") as get:
        get.return_value.status_code = 200
        get.return_value.json.return_value = {
            "results": [{"title": "t", "url": "https://x", "content": "c"}]}
        results = duck_search_mod.search("anything", 5, "at")
    assert results == [{"title": "t", "url": "https://x", "description": "c"}]
    ddgs.return_value.text.assert_not_called()

    # searxng down -> ddgs fallback serves
    def searx_down(query, max_results):
        return None

    with mock.patch("duck.search.DDGS") as ddgs, \
            mock.patch("duck.search.time.sleep"), \
            mock.patch.object(duck_search_mod, "_searxng_creds",
                              lambda: {"url": "https://sx.test", "auth": ("u", "p")}), \
            mock.patch.object(duck_search_mod, "_searxng_search", searx_down):
        ddgs.return_value.text.return_value = [
            {"href": "https://ddg", "body": "b"}]
        results = duck_search_mod.search("anything", 5, "at")
    assert results == [{"url": "https://ddg", "description": "b"}]
