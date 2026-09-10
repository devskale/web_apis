import io
import json
import logging
import multiprocessing
import os
import queue as queue_mod
import re
import resource
import secrets
import threading
import time
from datetime import datetime, timezone
import pdfplumber
import fitz
import httpx
import requests
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
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
# Coarse VA backstop for the child (MuPDF maps a lot of address space; the
# old 200MB killed even trivial conversions). Real RSS guard is the service
# cgroup MemoryMax (400M) — amd has ~1GB total RAM.
PDF_CHILD_RLIMIT_AS = 1024 * 1024 * 1024

LLAMA_PARSE_BASE = "https://api.cloud.llamaindex.ai"
# Polling budget must stay under the 120s gunicorn worker timeout.
LLAMA_POLL_TIMEOUT_S = 100
_LLAMA_POLL_INTERVAL_S = 3
LLAMA_TIERS = ("fast", "cost_effective", "agentic", "agentic_plus")

# ── Async jobs (llamaparse only) ──
# amd is a ~1GB box: ONE llamaparse job at a time, a small queue, and results
# that leave memory as soon as they are transferred to throway.
# Job state lives in JSON FILES under data/pdf_jobs/, not in memory: gunicorn
# runs 2 workers and polls must round-trip between them. Files also make jobs
# survive restarts and keep big markdown strings off the heap until requested.
PDF_ASYNC_PAGES = 40          # llamaparse beyond this is auto-async (~2s/page)
JOB_TTL_S = 2 * 3600          # done/failed jobs are evicted after 2h
MAX_JOBS = 10                 # queued+running+done; beyond -> 429
LLAMA_JOB_SLOTS = 1           # concurrent llamaparse conversions
THROWAY_URL = "https://skale.dev/throway/"
THROWAY_TTL_S = 14400         # 4h, per throway contract
THROWAY_TIMEOUT_S = 60
# Deployment-level kill switch: THROWAY_ENABLED=0 disables the transfer target
# (transfer=throway then answers 503). Default: enabled.
THROWAY_ENABLED = os.getenv("THROWAY_ENABLED", "1").strip().lower() in ("1", "true", "yes")

# ── Anti-zombie guarantees ──
# Every job has a hard deadline from creation. It is enforced at three points:
# 1. the worker won't wait for the conversion slot past the deadline,
# 2. the worker aborts before writing results past the deadline,
# 3. a status read flips overdue queued/running jobs to failed (self-healing,
#    covers a thread that hangs hard). Job FILES are evicted after JOB_TTL_S.
try:
    JOB_DEADLINE_S = int(os.getenv("PDF_JOB_DEADLINE_MIN", "20")) * 60
except ValueError:
    JOB_DEADLINE_S = 20 * 60

JOBS_DIR = os.path.join(os.path.dirname(__file__), "data", "pdf_jobs")
os.makedirs(JOBS_DIR, exist_ok=True)
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_llama_slots = threading.BoundedSemaphore(LLAMA_JOB_SLOTS)


def _job_path(job_id: str) -> str:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return os.path.join(JOBS_DIR, job_id + ".json")


def _save_job(job: dict) -> None:
    tmp = job["_path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in job.items() if not k.startswith("_")}, fh)
    os.replace(tmp, job["_path"])


def _load_job(job_id: str):
    try:
        with open(_job_path(job_id), encoding="utf-8") as fh:
            job = json.load(fh)
        job["_path"] = _job_path(job_id)
        return job
    except (OSError, ValueError):
        return None


def _purge_jobs() -> None:
    """Unlink expired job files and orphaned .tmp leftovers (opportunistic;
    atomic writes make this safe across the two workers)."""
    now = time.time()
    try:
        for name in os.listdir(JOBS_DIR):
            p = os.path.join(JOBS_DIR, name)
            try:
                if name.endswith(".tmp") or now - os.path.getmtime(p) > JOB_TTL_S:
                    os.unlink(p)
            except OSError:
                pass
    except OSError:
        pass


def _deadline_hit(job: dict) -> bool:
    return time.time() > job.get("deadline_ts", 0)


def _kill_overdue(job: dict) -> bool:
    """Flip an overdue queued/running job to failed (reader-side auto-kill).
    Returns True if the job was killed by this call."""
    if job.get("status") in ("queued", "running") and _deadline_hit(job):
        job["status"] = "failed"
        job["error"] = "auto-killed: job exceeded its deadline"
        _save_job(job)
        return True
    return False


def _count_jobs() -> int:
    try:
        return len([n for n in os.listdir(JOBS_DIR) if n.endswith(".json")])
    except OSError:
        return 0


def _throway_upload(markdown: str, name: str) -> str:
    safe = os.path.basename(name or "result.md") or "result.md"
    if not safe.lower().endswith(".md"):
        safe += ".md"
    resp = requests.post(
        THROWAY_URL,
        params={"name": safe},
        data=markdown.encode("utf-8"),
        headers={"Content-Type": "text/markdown; charset=utf-8"},
        timeout=THROWAY_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["url"]


def _run_llama_job(job_id: str, data: bytes, filename: str, tier: str,
                   language: str, transfer: str) -> None:
    """Background worker: poll llamaparse (I/O only), then optionally hand the
    result to throway. The markdown never lingers in memory - it goes straight
    to the job file / throway. Every stage checks the hard job deadline so no
    zombie job or thread survives it."""
    job = _load_job(job_id)

    # 1. never wait for the conversion slot past the deadline
    acquired = False
    while not _deadline_hit(job):
        if _llama_slots.acquire(timeout=5):
            acquired = True
            break
    if not acquired:
        job["status"] = "failed"
        job["error"] = "auto-killed: queued too long (deadline exceeded)"
        _save_job(job)
        return
    try:
        # 2. the conversion itself is bounded (LLAMA_POLL_TIMEOUT_S); abort
        #    before writing results past the deadline
        if _deadline_hit(job):
            job["status"] = "failed"
            job["error"] = "auto-killed: deadline exceeded before conversion"
            _save_job(job)
            return
        job["status"] = "running"
        _save_job(job)
        try:
            markdown = _llamaparse_to_markdown(
                data, filename, tier, language)
        except Exception as e:
            job["status"] = "failed"
            job["error"] = f"{type(e).__name__}: {e}"
            _save_job(job)
            return
        del data
        if _deadline_hit(job):
            job["status"] = "failed"
            job["error"] = "auto-killed: deadline exceeded after conversion"
            _save_job(job)
            return
        job["chars"] = len(markdown)
        if transfer == "throway":
            try:
                job["markdown_url"] = _throway_upload(markdown, filename)
                job["transfer"] = "throway"
                markdown = ""  # transferred: don't hold it in memory
            except Exception as e:
                logging.error("throway upload failed for job %s: %s", job_id, e)
                job["transfer_error"] = f"{type(e).__name__}: {e}"
        job["markdown"] = markdown
        job["status"] = "done"
        _save_job(job)
    finally:
        _llama_slots.release()


def _convert_local(data: bytes, method: str, out_q) -> None:
    """Child-process body for local conversion (see pdf_to_md).

    Never logs here: the child is spawned fresh, but keep it side-effect free.
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
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    parts.append(text)
            out_q.put(("ok", "\n\n".join(parts).strip()))
    except Exception as e:
        out_q.put(("error", f"{type(e).__name__}: {e}"))


def _public_base(request: Request) -> str:
    """Public base URL (behind nginx the worker doesn't honor proxy headers
    for base_url, so reconstruct it from forwarded headers + root_path)."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}{request.scope.get('root_path', '')}"


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
        "Extracts text from a PDF using the specified converter: pdfplumber (default, "
        "local) or llamaparse (LlamaParse cloud service - "
        "handles OCR and complex layouts; the document is uploaded to LlamaCloud). "
        "Limits: 10MB and 500 pages. Scanned PDFs without OCR will not yield text "
        "with the local converter. Returns markdown content and statistics."),
)
# Deliberately a sync endpoint: the conversion is CPU-bound, and FastAPI runs
# sync endpoints in the threadpool - an async def here would block the worker's
# event loop (and with it all other requests) for the whole conversion.
def pdf_to_md(
    file: UploadFile = File(...,
                            description="PDF file (≤10MB, ≤500 pages) to convert to Markdown-like text."),
    method: Literal["pdfplumber", "llamaparse"] = Query(
        "pdfplumber",
        description="Converter: 'pdfplumber' (default, local) or "
                    "'llamaparse' (cloud, OCR + complex layouts)."),
    tier: Literal["fast", "cost_effective", "agentic", "agentic_plus"] = Query(
        "fast",
        description="LlamaParse tier; only used with method=llamaparse."),
    language: str = Query(
        "de",
        description="OCR language hint (ISO code); only used with method=llamaparse."),
    wait: bool = Query(
        True,
        description="llamaparse only: false returns 202 + job_id immediately; "
                    "poll /pdf/jobs/{job_id}. Forced for documents beyond ~40 pages."),
    transfer: Literal["inline", "throway"] = Query(
        "inline",
        description="throway: result is uploaded to skale.dev/throway (4h TTL) and "
                    "only the link is returned — keeps responses small."),
    request: Request = None,
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

    if transfer == "throway" and not THROWAY_ENABLED:
        raise HTTPException(
            status_code=503, detail="throway transfer is disabled on this deployment.")

    if method == "pdfplumber":
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
        # Long documents must run as a background job: the sync request would
        # die at gunicorn's 120s timeout (~2s/page measured).
        if page_count > PDF_ASYNC_PAGES or not wait:
            _purge_jobs()
            if _count_jobs() >= MAX_JOBS:
                raise HTTPException(
                    status_code=429, headers={"Retry-After": "60"},
                    detail="Too many jobs queued; retry later.")
            job_id = secrets.token_urlsafe(12)
            job = {
                "job_id": job_id, "status": "queued",
                "created_ts": time.time(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "deadline_ts": time.time() + JOB_DEADLINE_S,
                "pages": page_count, "method": "llamaparse", "tier": tier,
                "_path": _job_path(job_id),
            }
            _save_job(job)
            threading.Thread(
                target=_run_llama_job,
                args=(job_id, data, filename, tier, language, transfer),
                daemon=True).start()
            return JSONResponse(status_code=202, content={
                "job_id": job_id, "status": "queued", "pages": page_count,
                "poll": _public_base(request) + f"/pdf/jobs/{job_id}",
                "auto_async": page_count > PDF_ASYNC_PAGES,
            })
        markdown = _llamaparse_to_markdown(data, filename, tier, language)

    if not markdown:
        raise HTTPException(status_code=422, detail="No text extracted")

    if transfer == "throway":
        try:
            url = _throway_upload(markdown, filename)
        except Exception as e:
            logging.error("throway transfer failed: %s", e)
            raise HTTPException(
                status_code=502, detail="throway transfer failed.")
        return {
            "filename": filename, "converter": method,
            "pages": page_count, "chars": len(markdown),
            "markdown_url": url, "expires_in": THROWAY_TTL_S,
        }

    return {
        "filename": filename,
        "converter": method,
        "pages": page_count,
        "chars": len(markdown),
        "markdown": markdown
    }


@router.get("/jobs/{job_id}", tags=["PDF"],
            summary="Status/result of an async pdf conversion job")
def pdf_job_status(job_id: str, token: str = Depends(verify_token)):
    _purge_jobs()
    job = _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    out = {k: job.get(k) for k in
           ("job_id", "status", "created_at", "pages", "chars")}
    out["expires_in"] = max(0, int(JOB_TTL_S - (time.time() - job["created_ts"])))
    if job["status"] == "failed":
        out["error"] = job.get("error", "")
    elif job["status"] in ("queued", "running") and _kill_overdue(job):
        out["status"] = "failed"
        out["error"] = job.get("error", "")
    if job["status"] == "done":
        if job.get("markdown_url"):
            out["markdown_url"] = job["markdown_url"]
            out["expires_in"] = THROWAY_TTL_S
        else:
            out["markdown"] = job.get("markdown", "")
    return out
