"""Box-wide throttle for DDG-family search calls (ddgs library).

The amd box is a datacenter IP that DDG soft-blocks when several searches
arrive in a burst. Gunicorn runs 2 worker *processes*, so an in-process
lock is not enough — this module serializes across processes via flock()
on duck/data/ddg.lock:

  * one ddgs call at a time (lock held for the whole call)
  * a minimum gap between the START of consecutive calls
  * a bounded queue wait — when the box is saturated, callers fail fast
    instead of piling on (a queued retry would only deepen the block)

Both call sites (duck/ducknews.py, duck/search.py) share the same lock,
so /duck/search, /duck/news and the SearXNG-fallback path all count
against one budget.

Tunables (env): DDG_MIN_INTERVAL (default 1.2s), DDG_MAX_WAIT (default 45s).
"""
import fcntl
import logging
import os
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_LOCK_DIR = os.path.join(os.path.dirname(__file__), "data")
_LOCK_PATH = os.path.join(_LOCK_DIR, "ddg.lock")

# Seconds between the start of consecutive DDG calls (box-wide).
MIN_INTERVAL = float(os.environ.get("DDG_MIN_INTERVAL", "1.2"))

# Max seconds to wait in queue for the lock before giving up.
MAX_WAIT = float(os.environ.get("DDG_MAX_WAIT", "45"))


class DdgThrottleTimeout(Exception):
    """Raised when a caller waited longer than MAX_WAIT for a slot."""


def _try_lock(fh) -> bool:
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


@contextmanager
def ddg_slot(min_interval: float = MIN_INTERVAL, max_wait: float = MAX_WAIT):
    """Serialize a DDG call box-wide and space consecutive starts.

    The previous call's start timestamp is kept in the lock file body;
    a fresh acquire sleeps the remaining gap before yielding.
    """
    os.makedirs(_LOCK_DIR, exist_ok=True)
    waited = False
    with open(_LOCK_PATH, "a+", encoding="utf-8") as fh:
        deadline = time.monotonic() + max_wait
        while not _try_lock(fh):
            waited = True
            if time.monotonic() >= deadline:
                raise DdgThrottleTimeout(
                    f"gave up after {max_wait:.0f}s in queue")
            time.sleep(min(0.25, max(0.05, deadline - time.monotonic())))
        if waited:
            logger.info("ddg throttle: acquired after queueing")
        try:
            last = 0.0
            try:
                fh.seek(0)
                last = float(fh.read().strip() or 0)
            except ValueError:
                pass
            gap = min_interval - (time.time() - last)
            if gap > 0:
                logger.info("ddg throttle: spacing sleep %.1fs", gap)
                time.sleep(gap)
            fh.seek(0)
            fh.truncate()
            fh.write(f"{time.time():.3f}\n")
            fh.flush()
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
