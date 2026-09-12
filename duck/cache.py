"""Disk-backed result cache for /duck/search (and friends).

Agents repeat identical queries constantly (same error messages, same
docs lookups). A TTL cache cuts upstream engine load without hurting
freshness: default 12h, 15min for time-limited queries (timelimit set).

Storage: one JSON file per query hash under duck/data/query_cache/,
capped at DUCK_CACHE_MAX entries (LRU by file mtime). amd is disk-tight:
1000 entries ≈ 10 MB worst case.
"""
import hashlib
import logging
import os
import time

logger = logging.getLogger(__name__)

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "query_cache")
_TTL_DEFAULT = float(os.environ.get("DUCK_CACHE_TTL_H", "12")) * 3600
_TTL_TIMELIMITED = float(os.environ.get("DUCK_CACHE_TTL_FRESH_S", "900"))
_MAX_ENTRIES = int(os.environ.get("DUCK_CACHE_MAX", "1000"))


def _key(final_query: str, **params) -> str:
    blob = repr((final_query, params))
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _ttl(timelimit) -> float:
    return _TTL_TIMELIMITED if timelimit else _TTL_DEFAULT


def cache_get(final_query: str, timelimit, **params):
    path = os.path.join(_CACHE_DIR, _key(final_query, **params))
    try:
        age = time.time() - os.path.getmtime(path)
        if age > _ttl(timelimit):
            os.unlink(path)
            return None
        with open(path, encoding="utf-8") as fh:
            import json
            entry = json.load(fh)
        # Refresh LRU position on hit.
        os.utime(path, None)
        logger.info("cache hit (%.0f min old)", age / 60)
        return entry.get("rows")
    except (OSError, ValueError):
        return None


def cache_put(final_query: str, timelimit, rows, **params) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, _key(final_query, **params))
    tmp = path + ".tmp"
    try:
        import json
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"rows": rows, "ts": time.time()}, fh)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("cache write failed: %s", e)
        return
    _evict_if_needed()


def _evict_if_needed() -> None:
    try:
        entries = [
            (os.path.getmtime(os.path.join(_CACHE_DIR, f)), f)
            for f in os.listdir(_CACHE_DIR)
        ]
    except OSError:
        return
    for _, oldest in sorted(entries)[:max(0, len(entries) - _MAX_ENTRIES)]:
        try:
            os.unlink(os.path.join(_CACHE_DIR, oldest))
        except OSError:
            pass
