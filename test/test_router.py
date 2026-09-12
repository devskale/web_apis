"""Tests for the SearXNG circuit breaker (open / half-open / closed)."""
import json
import time

import pytest


@pytest.fixture(autouse=True)
def _tmp_breaker(tmp_path, monkeypatch):
    monkeypatch.setattr("duck.router._BREAKER_PATH", str(tmp_path / "br.json"))
    return tmp_path / "br.json"


def _write_state(path, failures, opened_at):
    with open(path, "w") as fh:
        json.dump({"failures": failures, "opened_at": opened_at}, fh)


def test_closed_by_default():
    from duck.router import searxng_available
    assert searxng_available() is True


def test_opens_after_threshold_failures():
    from duck.router import record_searxng, searxng_available

    record_searxng(False)
    record_searxng(False)
    assert searxng_available() is False


def test_success_closes():
    from duck.router import record_searxng, searxng_available

    record_searxng(False)
    record_searxng(False)
    record_searxng(True)
    assert searxng_available() is True


def test_half_open_after_cooldown(_tmp_breaker):
    from duck.router import searxng_available

    _write_state(_tmp_breaker, 5, time.time() - 3600)  # opened long ago
    assert searxng_available() is True  # half-open: probe allowed


def test_failed_probe_reopens(_tmp_breaker):
    from duck.router import record_searxng, searxng_available

    _write_state(_tmp_breaker, 2, time.time() - 3600)
    record_searxng(False)  # probe fails -> reopen with fresh cooldown
    assert searxng_available() is False
