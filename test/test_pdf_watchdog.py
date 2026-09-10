"""Tests for the killable local-conversion child (malformed-PDF hardening)."""
import pdf.router as pr


def _convert(data: bytes, method: str):
    q = pr.multiprocessing.get_context("fork").Queue()
    pr._convert_local(data, method, q)
    return q.get(timeout=30)


def test_watchdog_converts_valid_pdf():
    data = open("/tmp/pdfmal/valid_min.pdf", "rb").read()
    status, md = _convert(data, "pymupdf4llm")
    assert status == "ok" and "Hallo Welt" in md


def test_watchdog_reports_conversion_error():
    status, msg = _convert(b"%PDF-1.4 junk but no structure", "pdfplumber")
    assert status == "error"


def test_watchdog_reports_child_error_not_crash():
    status, msg = _convert(b"", "pymupdf4llm")
    assert status == "error"
