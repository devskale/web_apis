"""Tests for async llamaparse jobs (wait=false, /pdf/jobs/{id}, throway)."""
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
    with pdf_router._jobs_lock:
        pdf_router._jobs.clear()


def _wait_done(job_id: str, tries: int = 100):
    for _ in range(tries):
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
