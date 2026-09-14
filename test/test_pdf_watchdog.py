"""Tests for the killable local-conversion child (malformed-PDF hardening)."""
import fitz

import pdf.router as pr


def _convert(data: bytes, method: str):
    q = pr.multiprocessing.get_context("fork").Queue()
    pr._convert_local(data, method, q)
    return q.get(timeout=30)


def test_watchdog_converts_valid_pdf():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hallo Welt")
    status, md = _convert(doc.tobytes(), "pdfplumber")
    assert status == "ok"  # text-layer extraction may be empty; ok == converted


def test_watchdog_reports_conversion_error():
    status, msg = _convert(b"%PDF-1.4 junk but no structure", "pdfplumber")
    assert status == "error"


def test_watchdog_reports_child_error_not_crash():
    status, msg = _convert(b"", "pdfplumber")
    assert status == "error"
