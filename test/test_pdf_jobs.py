"""Tests for async llamaparse jobs (wait=false, /pdf/jobs/{id}, throway)."""
import os
import time

import fitz
import pytest
from fastapi.testclient import TestClient

import main
import pdf.router as pdf_router

TOKEN = {"Authorization": "Bearer test-token"}

client = TestClient(main.app)


def _pdf(pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    return doc.tobytes()


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(pdf_router, "_LLAMA_POLL_INTERVAL_S", 0)
    monkeypatch.setattr(pdf_router, "_llama_api_key", lambda: "llx-test")
    monkeypatch.setattr(pdf_router, "_llamaparse_to_markdown",
                        lambda data, fn, tier, lang: "# converted")
    # Leichen aus früheren Läufen dürfen einen 429 (MAX_JOBS zählt
    # queued+running+done) nie auslösen — der Deckel gilt pro Test.
    monkeypatch.setattr(pdf_router, "MAX_JOBS", 10_000)
    _drain_slots()
    _clear_jobs_dir()
    yield
    # Joint die Worker-Threads BEVOR monkeypatch die gemockten Callables
    # zurücksetzt. Ohne das Join läuft ein Thread aus Test N weiter, während
    # Test N+1 bereits JOBS_DIR geleert und den echten (netzwerkfähigen!)
    # _llamaparse_to_markdown wiederhergestellt hat — der Thread hängt dann am
    # echten LlamaParse und schreibt seine Job-Datei zurück in das geleerte
    # Verzeichnis. Die Leiche treibt _count_jobs() Richtung MAX_JOBS und
    # flaked 202/429- und done-Assertions nondeterministisch.
    for t in list(pdf_router._job_threads):
        t.join(timeout=10)
    pdf_router._job_threads.clear()
    _drain_slots()
    _clear_jobs_dir()


def _drain_slots():
    """Release the 1-capacity conversion semaphore until it is fully free.

    Kapazität 1, freigegeben im Worker-finally. Unter Last (langsame Box) kann
    ein Worker den Slot länger halten als der Join timeout — ohne Drain wartet
    der nächste Test-Job bis zum acquire-timeout (5s) und das Poll-Budget des
    Tests läuft ab, während der Job noch 'queued' ist (der Flake).
    """
    while pdf_router._llama_slots._value < pdf_router.LLAMA_JOB_SLOTS:
        pdf_router._llama_slots.release()


def _clear_jobs_dir():
    for name in os.listdir(pdf_router.JOBS_DIR):
        os.unlink(os.path.join(pdf_router.JOBS_DIR, name))


def _wait_done(job_id: str, tries: int = 1500):
    """Poll until terminal, with enough budget to survive a slow worker.

    The conversion slot is a module-level semaphore with capacity 1: when a
    previous test's worker is still holding it, the next job waits in
    ``acquire(timeout=5)`` BEFORE it even starts — the poll budget must cover
    that stall, otherwise the test reads "queued" and asserts on the wrong
    state (this was the flake). 1500 x 10ms = 15 s — deliberately generous:
    _wait_done returns the moment the job is terminal, the budget only has to
    cover the worst case.
    """
    deadline = time.time() + tries * 0.01
    while time.time() < deadline:
        r = client.get(f"/pdf/jobs/{job_id}", headers=TOKEN)
        body = r.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.01)
    return body


def test_sync_llamaparse_still_works():
    r = client.post("/pdf/to_md?method=llamaparse", headers=TOKEN,
                    files={"file": ("a.pdf", _pdf(1), "application/pdf")})
    assert r.status_code == 200
    assert r.json()["markdown"] == "# converted"


def test_wait_false_returns_202_and_job_completes():
    r = client.post("/pdf/to_md?method=llamaparse&wait=false", headers=TOKEN,
                    files={"file": ("a.pdf", _pdf(2), "application/pdf")})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["poll"].endswith(f"/pdf/jobs/{body['job_id']}")
    assert body["auto_async"] is False

    done = _wait_done(body["job_id"])
    assert done["status"] == "done"
    assert done["markdown"] == "# converted"
    assert done["pages"] == 2


def test_big_document_forces_async(monkeypatch):
    monkeypatch.setattr(pdf_router, "PDF_ASYNC_PAGES", 1)
    r = client.post("/pdf/to_md?method=llamaparse", headers=TOKEN,
                    files={"file": ("a.pdf", _pdf(3), "application/pdf")})
    assert r.status_code == 202
    assert r.json()["auto_async"] is True


def test_throway_transfer_drops_markdown(monkeypatch):
    monkeypatch.setattr(pdf_router, "_throway_upload",
                        lambda md, name: f"https://skale.dev/throway/xyz-{name}")
    r = client.post(
        "/pdf/to_md?method=llamaparse&wait=false&transfer=throway",
        headers=TOKEN, files={"file": ("a.pdf", _pdf(1), "application/pdf")})
    assert r.status_code == 202
    done = _wait_done(r.json()["job_id"])
    assert done["status"] == "done"
    assert done["markdown_url"].startswith("https://skale.dev/throway/")
    assert "markdown" not in done


def test_failed_job_reports_error(monkeypatch):
    def boom(data, fn, tier, lang):
        raise RuntimeError("upstream down")
    monkeypatch.setattr(pdf_router, "_llamaparse_to_markdown", boom)
    r = client.post("/pdf/to_md?method=llamaparse&wait=false", headers=TOKEN,
                    files={"file": ("a.pdf", _pdf(1), "application/pdf")})
    done = _wait_done(r.json()["job_id"])
    assert done["status"] == "failed"
    assert "upstream down" in done["error"]


def test_unknown_job_404():
    assert client.get("/pdf/jobs/doesnotexist", headers=TOKEN).status_code == 404


def test_job_cap_returns_429(monkeypatch):
    monkeypatch.setattr(pdf_router, "MAX_JOBS", 0)
    r = client.post("/pdf/to_md?method=llamaparse&wait=false", headers=TOKEN,
                    files={"file": ("a.pdf", _pdf(1), "application/pdf")})
    assert r.status_code == 429


def test_jobs_need_token():
    r = client.post("/pdf/to_md?method=llamaparse&wait=false",
                    files={"file": ("a.pdf", _pdf(1), "application/pdf")})
    assert r.status_code == 401
    assert client.get("/pdf/jobs/whatever").status_code == 401


def test_throway_disabled_503(monkeypatch):
    monkeypatch.setattr(pdf_router, "THROWAY_ENABLED", False)
    r = client.post(
        "/pdf/to_md?method=llamaparse&wait=false&transfer=throway",
        headers=TOKEN, files={"file": ("a.pdf", _pdf(1), "application/pdf")})
    assert r.status_code == 503
    assert "disabled" in r.json()["detail"]


def test_reader_kills_overdue_job():
    """A hung worker (job stuck in running past its deadline) is flipped to
    failed by the next status read - no zombie state survives a poll."""
    import time as _t
    jid = "overduejob123"
    job = {"job_id": jid, "status": "running", "created_ts": _t.time() - 9999,
           "created_at": "x", "deadline_ts": _t.time() - 900, "pages": 5,
           "_path": pdf_router._job_path(jid)}
    pdf_router._save_job(job)
    body = client.get(f"/pdf/jobs/{jid}", headers=TOKEN).json()
    assert body["status"] == "failed"
    assert "auto-killed" in body["error"]


def test_worker_autokills_when_queued_too_long(monkeypatch):
    """deadline in the past at creation -> worker fails the job immediately
    instead of waiting for the conversion slot."""
    monkeypatch.setattr(pdf_router, "JOB_DEADLINE_S", -60)
    r = client.post("/pdf/to_md?method=llamaparse&wait=false", headers=TOKEN,
                    files={"file": ("a.pdf", _pdf(1), "application/pdf")})
    assert r.status_code == 202
    done = _wait_done(r.json()["job_id"])
    assert done["status"] == "failed"
    assert "auto-killed" in done["error"]


def test_no_payload_files_left_after_done():
    """RAM/disk hygiene: the spilled upload .pdf must be gone once the job
    reached a terminal state."""
    r = client.post("/pdf/to_md?method=llamaparse&wait=false", headers=TOKEN,
                    files={"file": ("a.pdf", _pdf(2), "application/pdf")})
    done = _wait_done(r.json()["job_id"])
    assert done["status"] == "done"
    leftovers = [n for n in os.listdir(pdf_router.JOBS_DIR) if n.endswith(".pdf")]
    assert leftovers == []
