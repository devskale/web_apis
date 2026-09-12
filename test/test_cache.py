"""Tests for the duck query cache (disk-backed, TTL + LRU cap)."""
import os
import time

import pytest


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("duck.cache._CACHE_DIR", str(tmp_path / "qc"))
    return tmp_path / "qc"


def test_roundtrip_and_distinct_keys():
    from duck import cache

    cache.cache_put("query a", None, [{"href": "x"}], max_results=10)
    cache.cache_put("query b", None, [{"href": "y"}], max_results=10)
    assert cache.cache_get("query a", None, max_results=10) == [{"href": "x"}]
    assert cache.cache_get("query b", None, max_results=10) == [{"href": "y"}]
    # different params -> different key
    assert cache.cache_get("query a", None, max_results=5) is None


def test_ttl_expiry_default(monkeypatch):
    from duck import cache

    cache.cache_put("q", None, [{"href": "x"}])
    path = next(iter(os.listdir(cache._CACHE_DIR)))
    full = os.path.join(cache._CACHE_DIR, path)
    old = time.time() - cache._TTL_DEFAULT - 60
    os.utime(full, (old, old))
    assert cache.cache_get("q", None) is None


def test_timelimited_queries_expire_faster():
    from duck import cache

    cache.cache_put("q", "d", [{"href": "x"}])
    path = os.path.join(cache._CACHE_DIR, next(iter(os.listdir(cache._CACHE_DIR))))
    # 10 min old: still fresh under the 12h default TTL, expired for a
    # timelimited query (15 min TTL). Note: a cache hit refreshes mtime
    # (LRU), so only ONE lookup may run against the aged file.
    old = time.time() - 600
    os.utime(path, (old, old))
    assert cache.cache_get("q", "d") is None


def test_lru_cap_evicts_oldest(monkeypatch):
    from duck import cache

    monkeypatch.setattr("duck.cache._MAX_ENTRIES", 2)
    cache.cache_put("q1", None, [1])
    time.sleep(0.02)
    cache.cache_put("q2", None, [2])
    time.sleep(0.02)
    cache.cache_put("q3", None, [3])
    assert cache.cache_get("q1", None) is None
    assert cache.cache_get("q2", None) == [2]
    assert cache.cache_get("q3", None) == [3]
