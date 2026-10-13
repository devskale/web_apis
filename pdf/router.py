import asyncio
import gc
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
from fastapi.responses import JSONResponse, StreamingResponse
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
# 2GB, not 1GB: pdfminer never touches 2GB of VA, but it RUNS INTO a 1GB
# cap — malloc fights the limit and the same child takes 3.4× longer
# (measured 2026-10-13: 60 pages 106.6s @1GB vs 31.6s @2GB, same spawn
# context). The cap is a bomb guard, not a budget — keep it out of the way.
PDF_CHILD_RLIMIT_AS = 2 * 1024 * 1024 * 1024

LLAMA_PARSE_BASE = "https://api.cloud.llamaindex.ai"
# Polling budget must stay under the 120s gunicorn worker timeout.
LLAMA_POLL_TIMEOUT_S = 100
_LLAMA_POLL_INTERVAL_S = 3
LLAMA_TIERS = ("fast", "cost_effective", "agentic", "agentic_plus")

# ── Async jobs (pdfplumber-local and llamaparse) ──
# amd is a ~1GB box: ONE llamaparse job at a time, a small queue, and results
# that leave memory as soon as they are transferred to throway.
# Job state lives in JSON FILES under data/pdf_jobs/, not in memory: gunicorn
# runs 2 workers and polls must round-trip between them. Files also make jobs
# survive restarts and keep big markdown strings off the heap until requested.
PDF_ASYNC_PAGES = 40          # llamaparse beyond this is auto-async (~2s/page)
# pdfplumber beyond this is auto-async too: amd converts ~0.5-0.8s/page, and
# the sync path must survive spawn-import + conversion inside the 60s child
# watchdog (which in turn must stay under gunicorn's 120s). 30 pages ≈ 25s
# worst case — margin, not optimism (issue 2026-10-13).
PDF_LOCAL_ASYNC_PAGES = 30
# Watchdog for the local child inside an async job: the worker thread has no
# gunicorn budget, the job deadline is the real cap. Floor at the sync value.
JOB_TTL_S = 2 * 3600          # done/failed jobs are evicted after 2h
MAX_JOBS = 10                 # queued+running+done; beyond -> 429
LLAMA_JOB_SLOTS = 1           # concurrent llamaparse conversions
LOCAL_JOB_SLOTS = 1           # concurrent local (pdfplumber) conversions — CPU-bound
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
# Boot marker for the orphan sweep: worker threads do not survive a restart,
# so any queued/running job older than this process is definitionally
# abandoned (SOTA visibility-timeout equivalent for a file-based queue —
# reclaimed on the first read after boot instead of waiting out the deadline).
_PROCESS_START = time.time()

_llama_slots = threading.BoundedSemaphore(LLAMA_JOB_SLOTS)
_local_slots = threading.BoundedSemaphore(LOCAL_JOB_SLOTS)
# Live job worker threads, kept in a registry so tests can join them before
# wiping shared state (JOBS_DIR) and prod can avoid zombie daemons on shutdown.
_job_threads: list[threading.Thread] = []
_job_threads_lock = threading.Lock()


def _job_path(job_id: str) -> str:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return os.path.join(JOBS_DIR, job_id + ".json")


def _save_job(job: dict) -> None:
    tmp = job["_path"] + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in job.items() if not k.startswith("_")}, fh)
        os.replace(tmp, job["_path"])
    except FileNotFoundError:
        # race vs _purge_jobs unlinking fresh .tmp files: rewrite once —
        # the job state itself is intact, only the temp file was reaped
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
    atomic writes make this safe across the two workers).

    Also the orphan sweep: queued/running jobs created before this process
    started can never finish (their worker threads died with the previous
    boot) — flip them to failed immediately instead of letting the client
    stare at 'running' for the rest of the 20-min deadline."""
    now = time.time()
    try:
        for name in os.listdir(JOBS_DIR):
            p = os.path.join(JOBS_DIR, name)
            try:
                if name.endswith(".json"):
                    _sweep_orphan(p, now)
                # .tmp: only reap STALE ones (>60s). A fresh .tmp is an
                # in-flight _save_job — unlinking it made os.replace fail and
                # silently killed the worker thread (race found by the new
                # catch-all, 2026-10-13).
                if ((name.endswith(".tmp") and now - os.path.getmtime(p) > 60)
                        or now - os.path.getmtime(p) > JOB_TTL_S):
                    os.unlink(p)
            except OSError:
                pass
    except OSError:
        pass


def _sweep_orphan(path: str, now: float) -> None:
    """Flip pre-boot queued/running jobs to failed (see _purge_jobs)."""
    try:
        with open(path, encoding="utf-8") as fh:
            job = json.load(fh)
        if (job.get("status") in ("queued", "running")
                and job.get("created_ts", now) < _PROCESS_START):
            job["status"] = "failed"
            job["error"] = "service restarted before the job finished (orphaned)"
            job["_path"] = path
            _save_job(job)
            logging.warning("pdf jobs: orphaned %s flipped to failed "
                            "(pre-boot, was %s)", os.path.basename(path),
                            job.get("method", "?"))
    except (OSError, ValueError):
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
    """ACTIVE jobs only (queued+running) — the queue cap protects CPU/RAM
    slots, not disk. A done result waiting for pickup (or TTL eviction)
    must never block new submissions for its whole TTL (issue: clients that
    never collect would lock the queue for 2h). Unreadable files count as
    active (conservative)."""
    n = 0
    try:
        for name in os.listdir(JOBS_DIR):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(JOBS_DIR, name), encoding="utf-8") as fh:
                    if json.load(fh).get("status") in ("queued", "running"):
                        n += 1
            except (OSError, ValueError):
                n += 1
        return n
    except OSError:
        return 0


def _job_cancelled(job_id: str) -> bool:
    """Fresh check whether a job was cancelled by the client (DELETE).
    Workers poll this before starting and after finishing their conversion —
    a cancelled job's result is discarded, never saved as done."""
    job = _load_job(job_id)
    return bool(job and job.get("status") == "cancelled")


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


def _cleanup_pdf(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _run_llama_job(job_id: str, pdf_path: str, filename: str, tier: str,
                   language: str, transfer: str) -> None:
    """Background worker: poll llamaparse (I/O only), then optionally hand the
    result to throway.

    RAM discipline (amd has ~1GB): the upload payload lives on DISK while the
    job is queued - bytes are read only after the conversion slot is acquired
    and released right after the conversion. gc.collect() returns big buffers
    to the OS immediately instead of at some later allocation. Every stage
    checks the hard job deadline so no zombie survives it."""
    job = _load_job(job_id)
    if job is None:
        # job file vanished (purge race) — nothing to do
        _cleanup_pdf(pdf_path)
        return

    # 1. never wait for the conversion slot past the deadline (zero heap while
    #    queued - the payload is on disk)
    acquired = False
    while not _deadline_hit(job):
        if _llama_slots.acquire(timeout=5):
            acquired = True
            break
    if not acquired:
        _cleanup_pdf(pdf_path)
        job["status"] = "failed"
        job["error"] = "auto-killed: queued too long (deadline exceeded)"
        _save_job(job)
        return
    data = None
    try:
        # 2. the conversion itself is bounded (LLAMA_POLL_TIMEOUT_S); abort
        #    before writing results past the deadline
        if _deadline_hit(job):
            job["status"] = "failed"
            job["error"] = "auto-killed: deadline exceeded before conversion"
            _save_job(job)
            return
        # cancelled while queued? the client DELETEd us — discard, don't run
        if _job_cancelled(job_id):
            return
        job["status"] = "running"
        _save_job(job)
        try:
            with open(pdf_path, "rb") as fh:
                data = fh.read()
        except OSError as e:
            job["status"] = "failed"
            job["error"] = f"OSError: {e}"
            _save_job(job)
            return
        # bounded retry for RETRYABLE upstream failures (LlamaParse hiccups:
        # 502/504). Permanent errors (quota 429, key 503, bad input) fail
        # fast — SOTA: retries are a designed policy, not a ladder you climb
        # into the same wall five times.
        markdown = None
        for attempt in range(2):
            try:
                markdown = _llamaparse_to_markdown(
                    data, filename, tier, language,
                    poll_budget_s=max(
                        LLAMA_POLL_TIMEOUT_S,
                        min(job["deadline_ts"] - time.time(), JOB_DEADLINE_S)
                        - 30.0))  # 30s margin: upload + result fetch + transfer
                break
            except Exception as e:
                # permanent = the API told us it will not work (quota 429,
                # key 503, bad input); everything else (502/504, network
                # resets) is worth exactly one retry with backoff
                permanent = (isinstance(e, HTTPException)
                             and e.status_code not in (502, 504))
                if permanent or attempt == 1 or _deadline_hit(job):
                    detail = (f"HTTP {e.status_code}: {e.detail}"
                              if isinstance(e, HTTPException)
                              else f"{type(e).__name__}: {e}")
                    job["status"] = "failed"
                    job["error"] = f"llamaparse: {detail}"
                    _save_job(job)
                    return
                logging.warning("pdf job %s: llamaparse retryable failure "
                                "(%s), retrying once", job_id,
                                type(e).__name__)
                time.sleep(10)  # backoff: immediate retries self-DDoS upstream
        del data
        gc.collect()
        if _deadline_hit(job):
            job["status"] = "failed"
            job["error"] = "auto-killed: deadline exceeded after conversion"
            _save_job(job)
            return
        # cancelled mid-conversion? discard the result, keep the cancelled
        # status the DELETE wrote — never overwrite it with done
        if _job_cancelled(job_id):
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
        del markdown
    except Exception as e:
        # worker crash = first-class failure event (SOTA DLQ rule): flip the
        # job NOW with the exception — never leave it 'running' until the
        # 20-min deadline flips it for us.
        logging.exception("pdf job %s: worker crashed", job_id)
        job["status"] = "failed"
        job["error"] = f"worker crashed: {type(e).__name__}: {e}"
        try:
            _save_job(job)
        except Exception:
            pass  # best effort — the reader-side sweep is the backstop
    finally:
        _llama_slots.release()
        _cleanup_pdf(pdf_path)
        data = None  # may already be unbound (del in try) — don't del again
        gc.collect()


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


def _run_pdfplumber_child(data: bytes, timeout_s: float) -> str:
    """Spawn the pdfplumber child, drain its queue, return the markdown.

    Zombie-safe in every path (issue 2026-10-13): the queue is drained BEFORE
    joining — mp.Queue pipes buffer ~64KB, and a bigger result deadlocks the
    child's feeder thread while the parent sits in join() (the documented
    multiprocessing deadlock; results >64KB used to die at the watchdog with
    the finished work discarded). 1s poll ticks make a crashed child fail
    fast with 500 instead of waiting out the whole budget as a 504.

    timeout_s is the child watchdog: 60s sync (under gunicorn's 120s kill);
    async jobs pass their remaining deadline budget.
    """
    ctx = multiprocessing.get_context("spawn")
    out_q = ctx.Queue()
    proc = ctx.Process(
        target=_convert_local, args=(data, "pdfplumber", out_q), daemon=True)
    proc.start()
    result = None
    deadline = time.monotonic() + timeout_s
    while result is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            result = out_q.get(timeout=min(remaining, 1.0))
        except queue_mod.Empty:
            if not proc.is_alive():
                proc.join()
                logging.error(
                    "pdf/to_md: pdfplumber child exited without result")
                raise HTTPException(
                    status_code=500, detail="PDF processing failed.")
    if result is None:
        proc.kill()
        proc.join()
        logging.error("pdf/to_md: pdfplumber child killed after %.0fs "
                      "(likely pathological PDF)", timeout_s)
        raise HTTPException(
            status_code=504, detail="PDF processing timed out.")
    status, payload = result
    # The feeder has flushed (get returned) — join cannot deadlock anymore.
    proc.join(5.0)
    if proc.is_alive():  # belt-and-braces: never leak a stray child
        proc.kill()
        proc.join()
    # Queue hygiene: an unclosed mp.Queue leaves a feeder thread + pipe FD
    # behind; at interpreter exit the resource_tracker stalls on them (seen
    # as a hang AFTER the test suite passes). close() + join_thread() is the
    # documented shutdown for queues we are done reading.
    out_q.close()
    out_q.join_thread()
    gc.collect()
    if status == "error":
        logging.error("pdf/to_md failed (pdfplumber): %s", payload)
        raise HTTPException(status_code=500, detail="PDF processing failed.")
    return payload


def _create_async_job(page_count: int, method: str, filename: str,
                       data: bytes, extra: dict) -> tuple:
    """Shared async-job creation: state file, disk spill, RAM discipline.

    Returns (job, pdf_path); the caller spawns its worker thread. Raises 429
    when the queue is full.
    """
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
        "pages": page_count, "method": method,
        "_path": _job_path(job_id),
    }
    job.update(extra)
    _save_job(job)
    # RAM: spill the upload payload to disk - queued jobs cost zero heap;
    # the worker reads it only while holding the slot.
    pdf_path = job["_path"][:-5] + ".pdf"
    with open(pdf_path, "wb") as fh:
        fh.write(data)
    return job, pdf_path


def _start_job_thread(worker, args) -> None:
    """Register + start a job worker daemon thread (shared housekeeping)."""
    thread = threading.Thread(target=worker, args=args, daemon=True)
    with _job_threads_lock:
        _job_threads[:] = [t for t in _job_threads if t.is_alive()]
        _job_threads.append(thread)
    thread.start()


def _run_local_job(job_id: str, pdf_path: str, filename: str,
                   transfer: str) -> None:
    """Background worker for async pdfplumber jobs (issue 2026-10-13).

    amd converts ~0.5-0.8s/page — documents beyond PDF_LOCAL_ASYNC_PAGES
    cannot fit the 60s sync watchdog (which must stay under gunicorn's 120s).
    Same RAM/deadline discipline as the llamaparse worker: payload on disk
    while queued, one CPU slot, hard deadline enforced at every stage.
    """
    job = _load_job(job_id)
    if job is None:
        _cleanup_pdf(pdf_path)
        return
    acquired = False
    while not _deadline_hit(job):
        if _local_slots.acquire(timeout=5):
            acquired = True
            break
    if not acquired:
        _cleanup_pdf(pdf_path)
        job["status"] = "failed"
        job["error"] = "auto-killed: queued too long (deadline exceeded)"
        _save_job(job)
        return
    data = None
    try:
        if _deadline_hit(job):
            job["status"] = "failed"
            job["error"] = "auto-killed: deadline exceeded before conversion"
            _save_job(job)
            return
        # cancelled while queued? discard, don't burn CPU on it
        if _job_cancelled(job_id):
            return
        job["status"] = "running"
        _save_job(job)
        try:
            with open(pdf_path, "rb") as fh:
                data = fh.read()
        except OSError as e:
            job["status"] = "failed"
            job["error"] = f"OSError: {e}"
            _save_job(job)
            return
        # No gunicorn budget in a worker thread: the job deadline (minus
        # margin, floored at the sync watchdog) is the child's real cap.
        budget = max(
            float(PDF_CONVERT_TIMEOUT_S),
            min(job["deadline_ts"] - time.time(), JOB_DEADLINE_S) - 30.0)
        try:
            markdown = _run_pdfplumber_child(data, budget)
        except HTTPException as e:
            job["status"] = "failed"
            job["error"] = f"conversion failed: {e.detail}"
            _save_job(job)
            return
        del data
        gc.collect()
        if _deadline_hit(job):
            job["status"] = "failed"
            job["error"] = "auto-killed: deadline exceeded after conversion"
            _save_job(job)
            return
        # cancelled mid-conversion? discard the result, keep cancelled
        if _job_cancelled(job_id):
            return
        job["chars"] = len(markdown)
        if transfer == "throway":
            try:
                job["markdown_url"] = _throway_upload(markdown, filename)
                job["transfer"] = "throway"
                markdown = ""
            except Exception as e:
                logging.error("throway upload failed for job %s: %s", job_id, e)
                job["transfer_error"] = f"{type(e).__name__}: {e}"
        job["markdown"] = markdown
        job["status"] = "done"
        _save_job(job)
        del markdown
    except Exception as e:
        # worker crash = first-class failure event: flip NOW, not at the
        # 20-min deadline (same rule as the llamaparse worker)
        logging.exception("pdf job %s: local worker crashed", job_id)
        job["status"] = "failed"
        job["error"] = f"worker crashed: {type(e).__name__}: {e}"
        try:
            _save_job(job)
        except Exception:
            pass
    finally:
        _local_slots.release()
        _cleanup_pdf(pdf_path)
        data = None
        gc.collect()


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
    poll_budget_s: float | None = None,
) -> str:
    """Upload to LlamaParse, poll the job, return the full markdown.

    v2 API: POST /parse/upload -> GET /parse/{id} (poll) -> expand=markdown_full.
    poll_budget_s: how long the LlamaParse job may take. Defaults to
    LLAMA_POLL_TIMEOUT_S (100s — the sync path must stay under gunicorn's
    120s kill). The async job worker passes its remaining job deadline:
    big scans (~2s/page) legitimately need minutes, and the 20-min job
    deadline — not the sync budget — is their cap (issue 2026-10-13).
    """
    budget = poll_budget_s if poll_budget_s is not None else LLAMA_POLL_TIMEOUT_S
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

        deadline = time.monotonic() + budget
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
        "with the local converter. Returns markdown content and statistics. "
        " Documents beyond ~30 pages (pdfplumber) / ~40 pages (llamaparse) are "
        "converted as async jobs automatically: the response is then 202 with a "
        "job_id - poll GET /pdf/jobs/{job_id} until done/failed."),
    responses={
        202: {
            "description": "Async job accepted (wait=false or llamaparse document "
                           "beyond ~40 pages). Poll GET /pdf/jobs/{job_id}.",
            "content": {"application/json": {"example": {
                "job_id": "M4w_SOjN5-JmmlXz", "status": "queued", "pages": 23,
                "poll": "https://amd.skale.dev/api/pdf/jobs/M4w_SOjN5-JmmlXz",
                "auto_async": False}}},
        },
        400: {"description": "Not a valid PDF (magic bytes / parse check)"},
        413: {"description": "PDF too large (max 10MB / 500 pages)"},
        422: {"description": "No text extracted (e.g. scan without OCR)"},
        429: {"description": "Rate limit, llamaparse quota, or job queue full"},
        502: {"description": "LlamaParse failure or throway transfer failed"},
        503: {"description": "LlamaParse key missing, or throway transfer disabled"},
        504: {"description": "Job deadline exceeded (default 20 min)"},
    })
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
        description="false returns 202 + job_id immediately (forces async for "
                    "both converters); poll /pdf/jobs/{job_id}. Forced "
                    "automatically beyond ~30 (pdfplumber) / ~40 (llamaparse) pages."),
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
        # Beyond PDF_LOCAL_ASYNC_PAGES the conversion cannot fit the 60s
        # child watchdog on this box (~0.5-0.8s/page + spawn import), and the
        # watchdog must stay under gunicorn's 120s kill. Route to an async
        # job instead — the client polls /pdf/jobs/{id} (same flow as
        # llamaparse). Small documents stay synchronous (fast path).
        if page_count > PDF_LOCAL_ASYNC_PAGES or not wait:
            job, pdf_path = _create_async_job(
                page_count, "pdfplumber", filename, data, {})
            del data
            gc.collect()
            _start_job_thread(
                _run_local_job, (job["job_id"], pdf_path, filename, transfer))
            return JSONResponse(status_code=202, content={
                "job_id": job["job_id"], "status": "queued",
                "pages": page_count,
                "poll": _public_base(request) + f"/pdf/jobs/{job['job_id']}",
                "auto_async": page_count > PDF_LOCAL_ASYNC_PAGES,
            })
        markdown = _run_pdfplumber_child(data, PDF_CONVERT_TIMEOUT_S)

    elif method == "llamaparse":
        # Cloud parsing: the document leaves this server (LlamaCloud, US).
        # Long documents must run as a background job: the sync request would
        # die at gunicorn's 120s timeout (~2s/page measured).
        if page_count > PDF_ASYNC_PAGES or not wait:
            job, pdf_path = _create_async_job(
                page_count, "llamaparse", filename, data,
                {"tier": tier})
            del data
            gc.collect()
            _start_job_thread(
                _run_llama_job,
                (job["job_id"], pdf_path, filename, tier, language, transfer))
            return JSONResponse(status_code=202, content={
                "job_id": job["job_id"], "status": "queued", "pages": page_count,
                "poll": _public_base(request) + f"/pdf/jobs/{job['job_id']}",
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


def _job_snapshot(job: dict) -> dict:
    """Public view of a job dict — the single source for BOTH the poll
    endpoint and the SSE stream, so they can never drift apart.

    Every snapshot carries expires_in (TTL seconds): how long the result
    stays retrievable — job files live JOB_TTL_S (2h); throway-transferred
    results live as long as the throway link (THROWAY_TTL_S, 4h)."""
    out = {k: job.get(k) for k in
           ("job_id", "status", "created_at", "pages", "chars")}
    out["expires_in"] = max(
        0, int(JOB_TTL_S - (time.time() - job.get("created_ts", 0))))
    if job.get("status") == "failed":
        out["error"] = job.get("error", "")
    if job.get("status") == "cancelled":
        out["error"] = "cancelled by client"
    if job.get("status") == "done":
        if job.get("markdown_url"):
            out["markdown_url"] = job["markdown_url"]
            out["expires_in"] = THROWAY_TTL_S
        else:
            out["markdown"] = job.get("markdown", "")
    return out


@router.get("/jobs/{job_id}/events", tags=["PDF"],
            summary="Server-Sent Events stream for a conversion job",
            description=(
                "Push stream of job status transitions. One event per status "
                "CHANGE (queued -> running -> done/failed), each carrying the "
                "same snapshot as GET /pdf/jobs/{id} incl. expires_in (TTL). "
                "A `: ping` comment every 15s keeps proxies from closing the "
                "stream; the stream ends on the terminal event. For a job "
                "that is already terminal, the event is emitted immediately "
                "and the stream closes — no waiting."),
            responses={
                200: {"description": "text/event-stream of status events"},
                404: {"description": "Unknown or expired job (jobs live ~2h)"},
            })
async def pdf_job_events(job_id: str, token: str = Depends(verify_token)):
    job = _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown or expired job")

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    async def stream():
        last = None
        # Hard caps: never stream longer than the job's own TTL — past it,
        # the file is purged and the result is gone (nothing left to wait for).
        stream_deadline = min(
            time.time() + JOB_TTL_S,
            job.get("created_ts", time.time()) + JOB_TTL_S + 30)
        last_beat = time.monotonic()
        while True:
            current = _load_job(job_id)
            if current is None:  # purged mid-stream (TTL eviction race)
                yield sse("status", {"status": "failed",
                                     "error": "job expired (TTL)",
                                     "expires_in": 0})
                return
            if current.get("status") in ("queued", "running"):
                _kill_overdue(current)  # same self-healing as the poll path
            status = current.get("status")
            if status != last:
                yield sse("status", _job_snapshot(current))
                last = status
                if status in ("done", "failed", "cancelled"):
                    return
            now = time.monotonic()
            if now - last_beat >= 15.0:  # proxy keep-alive comment
                yield ": ping\n\n"
                last_beat = now
            if now > stream_deadline:
                yield sse("status", {"status": "failed",
                                     "error": "stream exceeded job TTL",
                                     "expires_in": 0})
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/jobs/{job_id}", tags=["PDF"],
               summary="Cancel a job or purge its result",
               description=(
                   "Client abort:\n"
                   "- queued/running → status 'cancelled': workers discard the "
                   "job at their next checkpoint (before starting, or after "
                   "converting — results are never saved). A conversion "
                   "already in flight finishes CPU-bounded, its result is "
                   "dropped.\n"
                   "- done/failed → the job file is purged immediately "
                   "(manual TTL eviction — for results you will NOT pick "
                   "up, instead of waiting out the 2h TTL)."),
               responses={
                200: {"description": "cancelled / purged — body carries the "
                                     "resulting status"},
                404: {"description": "Unknown or expired job"},
            })
def pdf_job_delete(job_id: str, token: str = Depends(verify_token)):
    _purge_jobs()
    job = _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    status = job.get("status")
    if status in ("queued", "running"):
        job["status"] = "cancelled"
        _save_job(job)  # workers see it at their next checkpoint and discard
        return {"job_id": job_id, "status": "cancelled",
                "note": "workers discard this job at their next checkpoint"}
    # terminal (done/failed/cancelled): purge now — manual TTL eviction
    _cleanup_pdf(job["_path"][:-5] + ".pdf")
    os.unlink(job["_path"])
    return {"job_id": job_id, "status": "purged",
            "note": "result deleted before its TTL expired"}


@router.get("/jobs/{job_id}", tags=["PDF"],
            summary="Status/result of an async pdf conversion job",
            responses={
                200: {"description": "Current job status; on done includes markdown "
                                     "or markdown_url (transfer=throway)"},
                404: {"description": "Unknown or expired job (jobs live ~2h)"},
                429: {"description": "Rate limit"},
            })
def pdf_job_status(job_id: str, token: str = Depends(verify_token)):
    _purge_jobs()
    job = _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    if job["status"] in ("queued", "running"):
        _kill_overdue(job)
    return _job_snapshot(job)
