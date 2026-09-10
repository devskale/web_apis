"""Offline unit tests for the LlamaParse branch of pdf/to_md."""
import json
import sys
from unittest import mock

import httpx
import pytest
from fastapi import HTTPException

import pdf.router as pdf_router


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch):
    monkeypatch.setattr(pdf_router, "_LLAMA_POLL_INTERVAL_S", 0)


@pytest.fixture()
def fake_key(monkeypatch):
    """Stub the key resolver for tests that only exercise the HTTP flow."""
    monkeypatch.setattr(pdf_router, "_llama_api_key", lambda: "llx-test")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_happy_path_returns_markdown(fake_key):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/parse/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        if request.url.path.endswith("/parse/job-1"):
            if request.url.params.get("expand") == "markdown_full":
                return httpx.Response(
                    200, json={"markdown_full": "# Page 1\n\n---\n\n# Page 2"})
            return httpx.Response(200, json={"job": {"status": "COMPLETED"}})
        return httpx.Response(404)

    out = pdf_router._llamaparse_to_markdown(
        b"%PDF-fake", "doc.pdf", "fast", client=_client(handler))

    assert out == "# Page 1\n\n---\n\n# Page 2"
    upload = requests[0]
    assert upload.headers["Authorization"] == "Bearer llx-test"
    assert b'"tier": "fast"' in upload.content


def test_rejected_key_maps_to_502(fake_key):
    def handler(request):
        return httpx.Response(401, json={"detail": "Not authenticated"})

    with pytest.raises(HTTPException) as exc:
        pdf_router._llamaparse_to_markdown(
            b"%PDF-fake", "d.pdf", "fast", client=_client(handler))
    assert exc.value.status_code == 502


def test_quota_maps_to_429(fake_key):
    def handler(request):
        if request.url.path.endswith("/parse/upload"):
            return httpx.Response(402, json={"detail": "out of credits"})
        return httpx.Response(404)

    with pytest.raises(HTTPException) as exc:
        pdf_router._llamaparse_to_markdown(
            b"%PDF-fake", "d.pdf", "fast", client=_client(handler))
    assert exc.value.status_code == 429


def test_failed_job_maps_to_502(fake_key):
    def handler(request):
        if request.url.path.endswith("/parse/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(200, json={"status": "FAILED",
                                         "error_message": "boom"})

    with pytest.raises(HTTPException) as exc:
        pdf_router._llamaparse_to_markdown(
            b"%PDF-fake", "d.pdf", "fast", client=_client(handler))
    assert exc.value.status_code == 502


def test_poll_timeout_maps_to_504(fake_key, monkeypatch):
    monkeypatch.setattr(pdf_router, "LLAMA_POLL_TIMEOUT_S", 0)

    def handler(request):
        if request.url.path.endswith("/parse/upload"):
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(200, json={"status": "RUNNING"})

    with pytest.raises(HTTPException) as exc:
        pdf_router._llamaparse_to_markdown(
            b"%PDF-fake", "d.pdf", "fast", client=_client(handler))
    assert exc.value.status_code == 504


def test_key_prefers_env(monkeypatch):
    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "llx-env")
    assert pdf_router._llama_api_key() == "llx-env"


def test_key_unavailable_maps_to_503(monkeypatch):
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "credgoo", None)  # import -> ImportError
    with pytest.raises(HTTPException) as exc:
        pdf_router._llama_api_key()
    assert exc.value.status_code == 503
