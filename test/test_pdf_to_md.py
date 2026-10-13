"""Regression: /pdf/to_md mit method=pdfplumber bei großen Ergebnissen.

Issue 2026-10-13: der Parent jointe den Child, bevor er die mp.Queue las.
Die Pipe dahinter puffert ~64KB — größere Ergebnisse blockierten den
Feeder-Thread des Childs beim Exit, während der Parent in join() saß
(dokumentierter multiprocessing-Deadlock). Resultat: 504 nach exakt
PDF_CONVERT_TIMEOUT_S, die fertige Konvertierung wurde verworfen.

Diese Tests pinnen den Fix: Queue drainen VOR join (Poll mit 1s-Ticks,
crashed Child -> schnelles 500, hängender Child -> 504 zum Watchdog).
"""
import fitz
import pytest
from fastapi.testclient import TestClient

import main

TOKEN = {"Authorization": "Bearer test-token"}

client = TestClient(main.app)

# 64KB Pipe-Puffer: sauber darüber bleiben, damit der Test den Deadlock-Fall
# wirklich trifft (die Thesis im Vorfall: ~210KB bei 149 Seiten).
_PAGES = 50
_CHARS_PER_PAGE = 3000


def _text_pdf(pages: int = 1, chars_per_page: int = 100) -> bytes:
    """Echtes Text-PDF (pdfplumber muss Text finden, kein Scan)."""
    doc = fitz.open()
    filler = ("lorem ipsum dolor sit amet consectetur adipiscing elit " * 200)
    for i in range(pages):
        page = doc.new_page()
        page.insert_textbox(
            fitz.Rect(40, 40, 555, 800),
            f"Seite {i + 1}.\n" + filler[:chars_per_page],
            fontsize=9,
        )
    return doc.tobytes()


def test_pdfplumber_small_pdf_still_works():
    r = client.post(
        "/pdf/to_md?method=pdfplumber", headers=TOKEN,
        files={"file": ("small.pdf", _text_pdf(1, 500), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["converter"] == "pdfplumber"
    assert body["pages"] == 1
    assert "lorem ipsum" in body["markdown"]


def test_pdfplumber_large_result_no_deadlock(monkeypatch):
    """Regression Deadlock-Fix: Ergebnis deutlich >64KB im SYNC-Pfad.

    Vor dem Fix: join vor Queue-Drain -> mp.Queue-Deadlock, 504 nach 60s,
    fertige Arbeit verworfen. PDF_LOCAL_ASYNC_PAGES wird hochgepatcht, damit
    die 50 Seiten synchron laufen und wirklich den Sync-Pfad testen.
    """
    import pdf.router as pdf_router
    monkeypatch.setattr(pdf_router, "PDF_LOCAL_ASYNC_PAGES", 10_000)
    pdf_bytes = _text_pdf(_PAGES, _CHARS_PER_PAGE)
    r = client.post(
        "/pdf/to_md?method=pdfplumber", headers=TOKEN,
        files={"file": ("large.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pages"] == _PAGES
    # Der Deadlock-Kern: das Ergebnis muss ANGEKOMMEN sein, komplett.
    assert body["chars"] > 64 * 1024, (
        f"only {body['chars']} chars — result should exceed the 64KB pipe "
        "buffer to exercise the deadlock path")
    assert "Seite 50" in body["markdown"]
    assert "Seite 1" in body["markdown"]


def test_pdfplumber_auto_async_beyond_threshold():
    """>PDF_LOCAL_ASYNC_PAGES (30): 202 + Job, der durchläuft (issue
    2026-10-13: amd schafft ~0.5-0.8s/page — große Docs passen nicht in den
    60s-Sync-Watchdog und müssen als Job laufen, ohne gunicorn-Budget)."""
    import time

    import pdf.router as pdf_router
    pdf_bytes = _text_pdf(35, 2000)
    r = client.post(
        "/pdf/to_md?method=pdfplumber", headers=TOKEN,
        files={"file": ("big.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 202, r.text
    queued = r.json()
    assert queued["status"] == "queued"
    assert queued["auto_async"] is True
    assert queued["pages"] == 35

    deadline = time.time() + 60
    body = None
    while time.time() < deadline:
        body = client.get(f"/pdf/jobs/{queued['job_id']}",
                          headers=TOKEN).json()
        if body["status"] in ("done", "failed"):
            break
        time.sleep(0.2)
    assert body is not None and body["status"] == "done", body
    assert body["pages"] == 35
    assert "Seite 35" in body["markdown"]
    assert body["chars"] > 64 * 1024


@pytest.mark.parametrize("pages,chars", [(1, 100), (20, 100)])
def test_no_zombie_children_left(pages, chars):
    """Zombie-Sicherheit: nach der Konvertierung lebt kein Child mehr."""
    import multiprocessing as mp
    before = len(mp.active_children())
    r = client.post(
        "/pdf/to_md?method=pdfplumber", headers=TOKEN,
        files={"file": ("z.pdf", _text_pdf(pages, chars), "application/pdf")})
    assert r.status_code == 200
    # aktive Children aufräumen lassen (Daemon-Exit ist asynchron)
    for _ in range(50):
        if len(mp.active_children()) <= before:
            break
        import time
        time.sleep(0.1)
    assert len(mp.active_children()) <= before, (
        "leftover children after conversion — zombie leak")


def test_llamaparse_poll_budget_custom_is_honored(monkeypatch):
    """poll_budget_s wird eingehalten: kleines Budget + endlos PENDING ->
    504 beim Budget, nicht beim Sync-Default (100s).

    Gehört hierher (nicht zu test_pdf_jobs): deren autouse-Fixture mockt
    _llamaparse_to_markdown komplett — hier läuft die ECHTE Funktion.
    Issue 2026-10-13: große Scans brauchen im Job-Worker mehr als das
    Sync-Budget, das Budget muss also parametrisierbar sein.
    """
    import time

    import httpx
    import pdf.router as pdf_router
    from fastapi import HTTPException

    class _Resp:
        status_code = 200
        text = ""

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    class _NeverDoneClient:
        def __init__(self, *a, **kw):
            pass

        def post(self, *a, **kw):
            return _Resp({"id": "job-x"})

        def get(self, *a, **kw):
            return _Resp({"status": "PENDING"})

        def close(self):
            pass

    monkeypatch.setattr(pdf_router, "_llama_api_key", lambda: "llx-test")
    monkeypatch.setattr(pdf_router, "_LLAMA_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(httpx, "Client", _NeverDoneClient)
    t0 = time.monotonic()
    with pytest.raises(HTTPException) as excinfo:
        pdf_router._llamaparse_to_markdown(
            b"%PDF-1.5 fake", "s.pdf", "fast", "de", poll_budget_s=0.5)
    assert excinfo.value.status_code == 504
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, f"timeout took {elapsed}s — budget ignored"


def test_llamaparse_poll_budget_default_untouched(monkeypatch):
    """Ohne poll_budget_s gilt weiterhin LLAMA_POLL_TIMEOUT_S (Sync-Pfad:
    muss unter gunicorns 120s-Kill bleiben)."""
    import time

    import httpx
    import pdf.router as pdf_router
    from fastapi import HTTPException

    class _Resp:
        status_code = 200
        text = ""

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    class _NeverDoneClient:
        def __init__(self, *a, **kw):
            pass

        def post(self, *a, **kw):
            return _Resp({"id": "job-x"})

        def get(self, *a, **kw):
            return _Resp({"status": "PENDING"})

        def close(self):
            pass

    monkeypatch.setattr(pdf_router, "_llama_api_key", lambda: "llx-test")
    monkeypatch.setattr(pdf_router, "_LLAMA_POLL_INTERVAL_S", 0.05)
    monkeypatch.setattr(httpx, "Client", _NeverDoneClient)
    monkeypatch.setattr(pdf_router, "LLAMA_POLL_TIMEOUT_S", 0.6)
    t0 = time.monotonic()
    with pytest.raises(HTTPException) as excinfo:
        pdf_router._llamaparse_to_markdown(b"%PDF-1.5", "s.pdf", "fast", "de")
    assert excinfo.value.status_code == 504
    assert time.monotonic() - t0 < 5.0
