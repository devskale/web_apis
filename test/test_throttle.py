"""Tests for the box-wide DDG throttle (flock serialization + spacing).

Uses threads in one process — flock serializes within a process too, so
overlap detection works without spawning real workers. Cross-process
behavior was verified manually on amd (burst test, see git history).
"""
import threading
import time

import pytest

from duck.throttle import DdgThrottleTimeout, ddg_slot


def test_serializes_concurrent_calls():
    overlaps = []
    active = []
    lock = threading.Lock()

    def worker(i):
        with ddg_slot(min_interval=0.0):
            with lock:
                active.append(i)
            if len(active) > 1:
                overlaps.append(list(active))
            time.sleep(0.1)
            with lock:
                active.remove(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not overlaps, f"calls overlapped: {overlaps}"


def test_min_interval_spaces_starts():
    starts = []

    for _ in range(2):
        with ddg_slot(min_interval=0.3):
            starts.append(time.monotonic())

    assert starts[1] - starts[0] >= 0.25  # ~0.3 with scheduling slop


def test_queue_timeout_fails_fast():
    holder_done = threading.Event()
    released = threading.Event()

    def holder():
        with ddg_slot(min_interval=0.0):
            holder_done.set()
            released.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    assert holder_done.wait(timeout=2)

    try:
        with pytest.raises(DdgThrottleTimeout):
            with ddg_slot(min_interval=0.0, max_wait=0.2):
                pass  # never reached — holder still owns the lock
    finally:
        released.set()
        t.join()
