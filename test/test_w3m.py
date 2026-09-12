"""Offline unit tests for w3m helpers and the DDG-backed search."""
from unittest import mock

from w3m.w3m import get_numof_qresults
from duck.search import search as duck_search


def test_get_numof_qresults_picks_highest():
    assert get_numof_qresults("[1] a\n[2] b\n[12] c") == 12


def test_get_numof_qresults_ignores_non_numeric_brackets():
    assert get_numof_qresults("[x] y\n[3] z") == 3


def test_duck_search_maps_domain_to_region(monkeypatch):
    monkeypatch.setattr("duck.search._searxng_search", lambda q, n: None)
    with mock.patch("duck.search.DDGS") as ddgs:
        ddgs.return_value.text.return_value = iter(
            [{"href": "https://orf.at", "body": "news"}])
        results = duck_search("wetter", 5, "at")

    _, kwargs = ddgs.return_value.text.call_args
    assert kwargs["region"] == "at-at"
    assert results == [{"url": "https://orf.at", "description": "news"}]
