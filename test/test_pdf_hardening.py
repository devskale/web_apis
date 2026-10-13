"""Hardening tests: backend aborts, client cancels, never-picked-up results.

SOTA patterns mapped to this file-based queue (issue 2026-10-13):
- orphan sweep   = visibility-timeout reclaim: pre-boot queued/running jobs
                   are definitionally abandoned -> failed on first read
- worker crash   = first-class failure event: catch-all flips NOW, not at
                   the 20-min deadline
- DELETE /jobs   = client abort: cancel (workers discard) or manual TTL
                   eviction (purge a result nobody will pick up)
- active-only cap= done results waiting for pickup never block new submits
- llamaparse     = one bounded retry for retryable failures (502/504/network),
                   permanent ones (429/503) fail fast
"""
import json
import os
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
import pdf.router as pdf_router

TOKEN = {"Authorization": "Bearer test-token"}

client = TestClient(main.app)


def _write_job(job_id: str, status: str, created_ts=None, **extra):
    job = {"job_id": job_id, "status": status,
           "created_ts": created_ts if created_ts is not None else time.time(),
           "created_at": "x", "deadline_ts": time.time() + 1200,
           "pages": 5, "method": "pdfplumber",
           "_path": pdf_router._job_path(job_id)}
    job.update(extra)
    pdf_router._save_job(job)
    return job


@pytest.fixture(autouse=True)
def _clean():
    _clear()
    yield
    for t in list(pdf_router._job_threads):
        t.join(timeout=10)
    pdf_router._job_threads.clear()
    while pdf_router._llama_slots._value < pdf_router.LLAMA_JOB_SLOTS:
        pdf_router._llama_slots.release()
    while pdf_router._local_slots._value < pdf_router.LOCAL_JOB_SLOTS:
        pdf_router._local_slots.release()
    _clear()


def _clear():
    for name in os.listdir(pdf_router.JOBS_DIR):
        os.unlink(os.path.join(pdf_router.JOBS_DIR, name))


def test_orphan_sweep_flips_preboot_jobs():
    """Visibility-timeout equivalent: queued/running older than the process
    boot can never finish (threads died with the restart) -> failed on the
    next read, with an honest error."""
    _write_job("orphanedjob1", "running",
               created_ts=pdf_router._PROCESS_START - 3600)
    body = client.get("/pdf/jobs/orphanedjob1", headers=TOKEN).json()
    assert body["status"] == "failed"
    assert "restarted" in body["error"]

    _write_job("orphanedjob2", "queued",
               created_ts=pdf_router._PROCESS_START - 3600)
    body = client.get("/pdf/jobs/orphanedjob2", headers=TOKEN).json()
    assert body["status"] == "failed"

    # a job of THIS process is never swept
    _write_job("freshjob111", "running",
               created_ts=pdf_router._PROCESS_START + 1)
    body = client.get("/pdf/jobs/freshjob111", headers=TOKEN).json()
    assert body["status"] == "running"


def test_worker_crash_flips_failed_fast(monkeypatch):
    """Unexpected worker exception -> failed NOW with the exception name,
    never a silent 20-min 'running'."""
    def boom(data, timeout_s):
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr(pdf_router, "_run_pdfplumber_child", boom)
    monkeypatch.setattr(pdf_router, "PDF_LOCAL_ASYNC_PAGES", 0)  # jeder Job-Pfad
    import fitz
    doc = fitz.open()
    doc.new_page()
    r = client.post("/pdf/to_md?method=pdfplumber", headers=TOKEN,
                    files={"file": ("c.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.time() + 30
    body = {"status": "queued"}
    while time.time() < deadline:
        body = client.get(f"/pdf/jobs/{jid}", headers=TOKEN).json()
        if body["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert body["status"] == "failed"
    assert "worker crashed" in body["error"]
    assert "RuntimeError" in body["error"]


def test_delete_cancels_queued_job_and_worker_discards(monkeypatch):
    """DELETE on a queued job -> cancelled; the worker checks at its
    checkpoint and never runs (or never saves) the conversion."""
    release_events = []
    real_acquire = pdf_router._local_slots.acquire

    def slow_acquire(timeout=None):
        got = real_acquire(timeout=timeout)
        if got:
            time.sleep(0.3)  # window for the DELETE to land while "queued"
        return got

    monkeypatch.setattr(pdf_router._local_slots, "acquire", slow_acquire)
    monkeypatch.setattr(pdf_router, "PDF_LOCAL_ASYNC_PAGES", 0)  # Job-Pfad erzwingen

    import fitz
    doc = fitz.open()
    doc.new_page()
    r = client.post("/pdf/to_md?method=pdfplumber", headers=TOKEN,
                    files={"file": ("q.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 202
    jid = r.json()["job_id"]

    d = client.delete(f"/pdf/jobs/{jid}", headers=TOKEN)
    assert d.status_code == 200
    assert d.json()["status"] == "cancelled"

    time.sleep(1.5)  # let the worker pass its checkpoint
    body = client.get(f"/pdf/jobs/{jid}", headers=TOKEN).json()
    assert body["status"] == "cancelled"  # worker never overwrote it


def test_delete_purges_done_result(monkeypatch):
    """DELETE on a done job = manual TTL eviction: file gone immediately —
    the answer to 'I will never pick this up'."""
    _write_job("donejob9999", "done", markdown="# result")
    d = client.delete("/pdf/jobs/donejob9999", headers=TOKEN)
    assert d.status_code == 200
    assert d.json()["status"] == "purged"
    r = client.get("/pdf/jobs/donejob9999", headers=TOKEN)
    assert r.status_code == 404


def test_delete_unknown_404():
    assert client.delete("/pdf/jobs/doesnotexist7", headers=TOKEN).status_code == 404


def test_done_jobs_do_not_block_queue():
    """Queue cap counts ACTIVE jobs only: 10 unpicked done results must not
    429 the 11th submit (they cost disk, not CPU slots)."""
    for i in range(10):
        _write_job(f"doneresult{i:02d}", "done", markdown="x" * 10)
    import fitz
    doc = fitz.open()
    doc.new_page()
    doc_tobytes = doc.tobytes()
    # llamaparse sync path with mocked converter: proves the submit passes
    # the cap check without spinning up a local job
    orig = pdf_router._llamaparse_to_markdown
    pdf_router._llamaparse_to_markdown = (
        lambda data, fn, tier, lang, client=None, poll_budget_s=None: "# ok")
    try:
        r = client.post("/pdf/to_md?method=llamaparse", headers=TOKEN,
                        files={"file": ("k.pdf", doc_tobytes, "application/pdf")})
        assert r.status_code == 200, r.text  # not 429
    finally:
        pdf_router._llamaparse_to_markdown = orig


def test_llamaparse_job_retries_once_on_retryable(monkeypatch):
    """502 from LlamaParse (backend abort) -> exactly one retry with backoff,
    success on attempt 2 -> done."""
    calls = {"n": 0}

    def flaky(data, fn, tier, lang, client=None, poll_budget_s=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPException(status_code=502, detail="LlamaParse upload failed.")
        return "# retried ok"

    monkeypatch.setattr(pdf_router, "_llamaparse_to_markdown", flaky)
    monkeypatch.setattr(pdf_router, "LLAMA_POLL_TIMEOUT_S", 5)
    import fitz
    doc = fitz.open()
    doc.new_page()
    r = client.post("/pdf/to_md?method=llamaparse&wait=false", headers=TOKEN,
                    files={"file": ("r.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.time() + 60
    body = {"status": "queued"}
    while time.time() < deadline:
        body = client.get(f"/pdf/jobs/{jid}", headers=TOKEN).json()
        if body["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert body["status"] == "done", body
    assert calls["n"] == 2


def test_llamaparse_job_fails_fast_on_permanent(monkeypatch):
    """429 (quota) is permanent: no retry, immediate failed."""
    calls = {"n": 0}

    def quota(data, fn, tier, lang, client=None, poll_budget_s=None):
        calls["n"] += 1
        raise HTTPException(status_code=429, detail="quota exhausted")

    monkeypatch.setattr(pdf_router, "_llamaparse_to_markdown", quota)
    import fitz
    doc = fitz.open()
    doc.new_page()
    r = client.post("/pdf/to_md?method=llamaparse&wait=false", headers=TOKEN,
                    files={"file": ("p.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.time() + 30
    body = {"status": "queued"}
    while time.time() < deadline:
        body = client.get(f"/pdf/jobs/{jid}", headers=TOKEN).json()
        if body["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert body["status"] == "failed"
    assert "429" in body["error"]
    assert calls["n"] == 1  # no retry wasted on a permanent error
