import io
import json
import logging
import multiprocessing
import os
import queue as queue_mod
import resource
import tempfile
import time
import pdfplumber
import pymupdf4llm
import fitz
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from auth import verify_token
from typing import Literal

router = APIRouter()

MAX_PDF_BYTES = 10 * 1024 * 1024
# Conversion is CPU/RAM-heavy and the service runs with MemoryMax, so one
# pathological PDF must not be able to take down the whole service.
MAX_PDF_PAGES = 500
# Local conversion runs in a killable child process: decompression bombs or
# huge streams can hang a parser indefinitely; the child is killed at the
# deadline (well under the 120s gunicorn worker timeout) and capped in memory.
PDF_CONVERT_TIMEOUT_S = 60
# amd has ~1GB total RAM (MemoryMax 400M for the whole service); the child
# must stay well inside that budget.
PDF_CHILD_RLIMIT_AS = 200 * 1024 * 1024

LLAMA_PARSE_BASE = "https://api.cloud.llamaindex.ai"
# Polling budget must stay under the 120s gunicorn worker timeout.
LLAMA_POLL_TIMEOUT_S = 100
_LLAMA_POLL_INTERVAL_S = 3
LLAMA_TIERS = ("fast", "cost_effective", "agentic", "agentic_plus")


def _convert_local(data: bytes, method: str, out_q) -> None:
    """Child-process body for local conversion (see pdf_to_md).

    Never logs here: the child is forked from a threaded worker, and logging
    locks may be held at fork time.
    """
    try:
        # Cap address space (backstop vs. decompression bombs). Best effort:
        # macOS refuses to lower RLIMIT_AS from unlimited (fine — dev only);
        # Linux (production) honors it. Never let this break conversion.
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            cap = (PDF_CHILD_RLIMIT_AS if soft == resource.RLIM_INFINITY
                   else min(soft, PDF_CHILD_RLIMIT_AS))
            resource.setrlimit(resource.RLIMIT_AS, (cap, hard))
        except (ValueError, OSError):
            pass
        if method == "pdfplumber":
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                parts = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text:
                        parts.append(text)
                out_q.put(("ok", "\n\n".join(parts).strip()))
        else:  # pymupdf4llm
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            try:
                with os.fdopen(fd, "wb") as tmp:
                    tmp.write(data)
                out_q.put(("ok", pymupdf4llm.to_markdown(tmp_path)))
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
    except Exception as e:
        out_q.put(("error", f"{type(e).__name__}: {e}"))


def _llama_api_key() -> str:
    """Resolve the LlamaCloud API key: env/.env first, credgoo fallback."""
    key = os.getenv("LLAMA_CLOUD_API_KEY", "").strip()
    if key:
        return key
    try:
        from credgoo import get_api_key
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail=("LlamaParse not configured: set LLAMA_CLOUD_API_KEY "
                    "(credgoo is not installed)."))
    try:
        key = (get_api_key("llamacloud") or "").strip()
    except Exception:
        logging.exception("credgoo llamacloud resolution failed")
        key = ""
    if not key:
        raise HTTPException(
            status_code=503,
            detail=("LlamaParse not configured: set LLAMA_CLOUD_API_KEY or "
                    "set up credgoo service 'llamacloud'."))
    return key


def _llamaparse_to_markdown(
    data: bytes,
    filename: str,
    tier: str,
    language: str,
    client: httpx.Client | None = None,
) -> str:
    """Upload to LlamaParse, poll the job, return the full markdown.

    v2 API: POST /parse/upload -> GET /parse/{id} (poll) -> expand=markdown_full.
    """
    headers = {"Authorization": f"Bearer {_llama_api_key()}"}
    config: dict = {
        "tier": tier,
        "version": "latest",
        "processing_options": {
            "ocr_parameters": {"languages": [language]} if language else {},
        },
        "output_options": {
            "markdown": {"tables": {"output_tables_as_markdown": True}},
        },
    }
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=30)
    try:
        resp = client.post(
            f"{LLAMA_PARSE_BASE}/api/v2/parse/upload",
            headers=headers,
            files={"file": (filename, data, "application/pdf")},
            data={"configuration": json.dumps(config)},
        )
        if resp.status_code in (401, 403):
            logging.error("llamaparse rejected the API key: %s %s",
                          resp.status_code, resp.text[:200])
            raise HTTPException(
                status_code=502, detail="LlamaParse rejected the API key.")
        if resp.status_code in (402, 429):
            raise HTTPException(
                status_code=429, detail="LlamaParse quota or rate limit exhausted.")
        if resp.status_code >= 400:
            logging.error("llamaparse upload failed: %s %s",
                          resp.status_code, resp.text[:200])
            raise HTTPException(
                status_code=502, detail="LlamaParse upload failed.")
        job_id = resp.json().get("id")
        if not job_id:
            raise HTTPException(
                status_code=502, detail="LlamaParse returned no job id.")

        deadline = time.monotonic() + LLAMA_POLL_TIMEOUT_S
        while True:
            time.sleep(_LLAMA_POLL_INTERVAL_S)
            check = client.get(
                f"{LLAMA_PARSE_BASE}/api/v2/parse/{job_id}", headers=headers)
            if check.status_code >= 400:
                logging.error("llamaparse status check failed: %s %s",
                              check.status_code, check.text[:200])
                raise HTTPException(
                    status_code=502, detail="LlamaParse job status failed.")
            body = check.json()
            # v2 nests job fields on GET; accept both shapes defensively.
            status = body.get("status") or body.get("job", {}).get("status")
            if status == "COMPLETED":
                break
            if status in ("FAILED", "CANCELLED"):
                error = (body.get("error_message")
                         or body.get("job", {}).get("error_message") or "")
                logging.error("llamaparse job %s ended %s: %s",
                              job_id, status, error)
                raise HTTPException(
                    status_code=502, detail="LlamaParse job failed.")
            if time.monotonic() > deadline:
                raise HTTPException(
                    status_code=504, detail="LlamaParse job timed out.")

        result = client.get(
            f"{LLAMA_PARSE_BASE}/api/v2/parse/{job_id}",
            headers=headers,
            params={"expand": "markdown_full"},
        )
        if result.status_code >= 400:
            logging.error("llamaparse result fetch failed: %s %s",
                          result.status_code, result.text[:200])
            raise HTTPException(
                status_code=502, detail="LlamaParse result fetch failed.")
        return (result.json().get("markdown_full") or "").strip()
    finally:
        if own_client:
            client.close()


@router.post(
    "/to_md",
    tags=["PDF"],
    summary="Convert PDF to Markdown-like text",
    description=(
        "Extracts text from a PDF using the specified converter: pymupdf4llm (default, "
        "local, no OCR), pdfplumber (local), or llamaparse (LlamaParse cloud service - "
        "handles OCR and complex layouts; the document is uploaded to LlamaCloud). "
        "Limits: 10MB and 500 pages. Scanned PDFs without OCR will not yield text "
        "with the local converters. Returns markdown content and statistics."),
)
# Deliberately a sync endpoint: the conversion is CPU-bound, and FastAPI runs
# sync endpoints in the threadpool - an async def here would block the worker's
# event loop (and with it all other requests) for the whole conversion.
def pdf_to_md(
    file: UploadFile = File(...,
                            description="PDF file (≤10MB, ≤500 pages) to convert to Markdown-like text."),
    method: Literal["pymupdf4llm", "pdfplumber", "llamaparse"] = Query(
        "pymupdf4llm",
        description="Converter: 'pymupdf4llm' (default, local), 'pdfplumber' (local), "
                    "or 'llamaparse' (cloud, OCR + complex layouts)."),
    tier: Literal["fast", "cost_effective", "agentic", "agentic_plus"] = Query(
        "fast",
        description="LlamaParse tier; only used with method=llamaparse."),
    language: str = Query(
        "de",
        description="OCR language hint (ISO code); only used with method=llamaparse."),
    token: str = Depends(verify_token),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Reject oversized uploads before buffering the body in memory. size is
    # known from the multipart parsing; the post-read check stays as a guard
    # for clients that lie about it.
    if file.size is not None and file.size > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    data = file.file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413, detail="File too large (max 10MB)")

    # Header sniff + a real parse: garbage with a .pdf name gets a clean 400
    # instead of a converter traceback. The spec puts the header at byte 0,
    # but tolerating the first 1KB matches what PDF viewers accept.
    if b"%PDF-" not in data[:1024]:
        raise HTTPException(status_code=400, detail="File is not a valid PDF")

    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            page_count = doc.page_count
    except Exception:
        raise HTTPException(status_code=400, detail="File is not a valid PDF")

    if page_count > MAX_PDF_PAGES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF has too many pages (max {MAX_PDF_PAGES})")

    if method in ("pdfplumber", "pymupdf4llm"):
        # Watchdog: the conversion runs in a killable child. A pathological
        # PDF (decompression bomb, huge stream) gets 504 at the deadline
        # instead of tying the worker up until gunicorn's 120s kill.
        # spawn (not fork): forking from a request thread of a threaded
        # worker inherits held locks and deadlocks the child.
        ctx = multiprocessing.get_context("spawn")
        out_q = ctx.Queue()
        proc = ctx.Process(
            target=_convert_local, args=(data, method, out_q), daemon=True)
        proc.start()
        proc.join(PDF_CONVERT_TIMEOUT_S)
        if proc.is_alive():
            proc.kill()
            proc.join()
            logging.error("pdf/to_md: %s child killed after %ss (likely "
                          "pathological PDF)", method, PDF_CONVERT_TIMEOUT_S)
            raise HTTPException(
                status_code=504, detail="PDF processing timed out.")
        try:
            status, payload = out_q.get_nowait()
        except queue_mod.Empty:
            logging.error("pdf/to_md: %s child exited without result", method)
            raise HTTPException(
                status_code=500, detail="PDF processing failed.")
        if status == "error":
            logging.error("pdf/to_md failed (%s): %s", method, payload)
            raise HTTPException(
                status_code=500, detail="PDF processing failed.")
        markdown = payload

    elif method == "llamaparse":
        # Cloud parsing: the document leaves this server (LlamaCloud, US).
        markdown = _llamaparse_to_markdown(data, filename, tier, language)

    if not markdown:
        raise HTTPException(status_code=422, detail="No text extracted")

    return {
        "filename": filename,
        "converter": method,
        "pages": page_count,
        "chars": len(markdown),
        "markdown": markdown
    }
