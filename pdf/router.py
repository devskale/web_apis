import io
import logging
import os
import tempfile
import pdfplumber
import pymupdf4llm
import fitz
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from auth import verify_token
from typing import Literal

router = APIRouter()

MAX_PDF_BYTES = 10 * 1024 * 1024
# Conversion is CPU/RAM-heavy and the service runs with MemoryMax=400M, so one
# pathological PDF must not be able to take down the whole service.
MAX_PDF_PAGES = 500


@router.post(
    "/to_md",
    tags=["PDF"],
    summary="Convert PDF to Markdown-like text",
    description=(
        "Extracts text from a PDF using the specified converter (pymupdf4llm or pdfplumber). "
        "Limits: 10MB and 500 pages. Scanned PDFs without OCR will not yield text. "
        "Returns markdown content and statistics."),
)
# Deliberately a sync endpoint: the conversion is CPU-bound, and FastAPI runs
# sync endpoints in the threadpool - an async def here would block the worker's
# event loop (and with it all other requests) for the whole conversion.
def pdf_to_md(
    file: UploadFile = File(...,
                            description="PDF file (≤10MB, ≤500 pages) to convert to Markdown-like text."),
    method: Literal["pymupdf4llm", "pdfplumber"] = Query(
        "pymupdf4llm", description="Converter to use: 'pymupdf4llm' (default) or 'pdfplumber'."),
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

    if method == "pdfplumber":
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                parts = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text:
                        parts.append(text)
                markdown = "\n\n".join(parts).strip()
        except Exception:
            logging.exception("pdf/to_md failed (pdfplumber)")
            raise HTTPException(
                status_code=500, detail="PDF processing failed.")

    elif method == "pymupdf4llm":
        try:
            # pymupdf4llm expects a file path
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            try:
                markdown = pymupdf4llm.to_markdown(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception:
            logging.exception("pdf/to_md failed (pymupdf4llm)")
            raise HTTPException(
                status_code=500, detail="PDF processing failed.")

    if not markdown:
        raise HTTPException(status_code=422, detail="No text extracted")

    return {
        "filename": filename,
        "converter": method,
        "pages": page_count,
        "chars": len(markdown),
        "markdown": markdown
    }
