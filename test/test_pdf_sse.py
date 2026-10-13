"""SSE-Stream für Konvertierungs-Jobs: GET /pdf/jobs/{id}/events.

Ein Event pro Statuswechsel (queued -> running -> done/failed), jedes mit
dem gleichen Snapshot wie der Poll-Endpoint inkl. expires_in (TTL).
Terminaler Job → sofortiges Event + Stream-Ende. Heartbeat-Kommentare
halten Proxys offen. Der Stream läuft nie länger als die Job-TTL.
"""
import json
import time

import fitz
import pytest
from fastapi.testclient import TestClient

import main
import pdf.router as pdf_router

TOKEN = {"Authorization": "Bearer test-token"}

client = TestClient(main.app)


def _pdf(pages: int = 1) -> bytes:
    """Echtes Text-PDF: pdfplumber-Jobs laufen real (nicht gemockt) und
    müssen Text liefern — leere Seiten würden leeres Markdown ergeben."""
    doc = fitz.open()
    filler = ("lorem ipsum dolor sit amet consectetur adipiscing elit " * 200)
    for i in range(pages):
        page = doc.new_page()
        page.insert_textbox(
            fitz.Rect(40, 40, 555, 800),
            f"Seite {i + 1}.\n" + filler[:2000], fontsize=9)
    return doc.tobytes()


@pytest.fixture(autouse=True)
def _jobs_clean():
    _clear_jobs_dir()
    pdf_router._local_slots.release() if pdf_router._local_slots._value == 0 else None
    yield
    for t in list(pdf_router._job_threads):
        t.join(timeout=10)
    pdf_router._job_threads.clear()
    while pdf_router._local_slots._value < pdf_router.LOCAL_JOB_SLOTS:
        pdf_router._local_slots.release()
    _clear_jobs_dir()


def _clear_jobs_dir():
    import os
    for name in os.listdir(pdf_router.JOBS_DIR):
        os.unlink(os.path.join(pdf_router.JOBS_DIR, name))


def _collect_events(job_id: str, max_events: int = 10, timeout: float = 90):
    """Stream lesen bis Stream-Ende oder Limit; liefert die data-Dicts."""
    events = []
    with client.stream("GET", f"/pdf/jobs/{job_id}/events",
                       headers=TOKEN, timeout=timeout) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        event_name = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: ") and event_name:
                events.append(json.loads(line[len("data: "):]))
                if len(events) >= max_events:
                    break
    return events


def _submit_async_job(pages: int = 35) -> str:
    r = client.post("/pdf/to_md?method=pdfplumber", headers=TOKEN,
                    files={"file": ("job.pdf", _pdf(pages), "application/pdf")})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def test_sse_streams_transitions_with_ttl():
    """queued -> running -> done als Einzel-Events, JEDES mit expires_in."""
    job_id = _submit_async_job()
    events = _collect_events(job_id)
    statuses = [e["status"] for e in events]
    assert statuses[-1] == "done", events
    assert "running" in statuses, events  # mindestens ein Zwischenstatus
    # TTL-Pflicht: jedes Event trägt expires_in > 0 (Ergebnis noch holbar)
    for e in events:
        assert "expires_in" in e and e["expires_in"] > 0, e
    assert events[-1]["chars"] > 0


def test_sse_done_includes_markdown_and_ttl():
    """Terminal-Event liefert das Ergebnis wie der Poll-Endpoint."""
    job_id = _submit_async_job()
    events = _collect_events(job_id)
    done = events[-1]
    assert done["status"] == "done"
    assert done["markdown"]  # vollständiges Ergebnis im letzten Event
    assert done["expires_in"] > 0


def test_sse_terminal_job_emits_immediately():
    """Bereits terminierter Job: genau ein Event, Stream endet sofort."""
    job_id = _submit_async_job()
    _wait_terminal(job_id)
    t0 = time.monotonic()
    events = _collect_events(job_id, max_events=5)
    assert len(events) == 1, events
    assert events[0]["status"] == "done"
    assert time.monotonic() - t0 < 5.0  # kein Künstliches Warten


def test_sse_unknown_job_404():
    r = client.get("/pdf/jobs/doesnotexist99/events", headers=TOKEN)
    assert r.status_code == 404


def test_sse_requires_token():
    r = client.get("/pdf/jobs/whatever1/events")
    assert r.status_code == 401


def _wait_terminal(job_id: str, tries: int = 1500):
    deadline = time.time() + tries * 0.01
    body = {"status": "queued"}
    while time.time() < deadline:
        body = client.get(f"/pdf/jobs/{job_id}", headers=TOKEN).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.01)
    return body
