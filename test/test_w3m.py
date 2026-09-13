"""Offline unit tests for the DDG-backed search used by /w3m_google."""
from unittest import mock

from duck.search import search as duck_search


def test_duck_search_maps_domain_to_region(monkeypatch):
    monkeypatch.setattr("duck.search._searxng_search", lambda q, n, lang=None: None)
    with mock.patch("duck.search.DDGS") as ddgs:
        ddgs.return_value.text.return_value = iter(
            [{"href": "https://orf.at", "body": "news"}])
        results = duck_search("wetter", 5, "at")

    _, kwargs = ddgs.return_value.text.call_args
    assert kwargs["region"] == "at-at"
    assert results == [{"url": "https://orf.at", "description": "news"}]
