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


def test_search_web_prefers_searxng():
    # searxng serves -> ddgs never called
    with mock.patch("duck.ducknews._searxng_search") as sx, \
            mock.patch("duck.ducknews.DDGS") as ddgs:
        sx.return_value = [{"title": "T", "url": "https://sx",
                            "description": "d"}]
        results = search_web("query", site="github.com")
    assert results == [{"title": "T", "href": "https://sx", "body": "d"}]
    ddgs.return_value.text.assert_not_called()
    assert sx.call_args[0][0] == "query site:github.com"
    assert sx.call_args[1].get("time_range") is None


def test_search_web_falls_back_to_ddgs_when_searxng_down():
    with mock.patch("duck.ducknews._searxng_search", return_value=None), \
            mock.patch("duck.ducknews.DDGS") as ddgs:
        ddgs.return_value.text.return_value = [
            {"title": "t", "href": "u", "body": "b"}]
        results = search_web("query")
    assert results and results[0]["href"] == "u"
    ddgs.return_value.text.assert_called_once()


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
