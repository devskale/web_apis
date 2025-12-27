import io
import pdfplumber
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from auth import verify_token

router = APIRouter()


@router.post(
    "/to_md",
    tags=["PDF"],
    summary="Convert PDF to Markdown-like text",
    description=(
        "Extracts text from a PDF using pdfplumber and returns it as a Markdown-like string. "
        "Limit: 10MB. Scanned PDFs without OCR will not yield text."),
)
async def pdf_to_md(
    file: UploadFile = File(...,
                            description="PDF file (≤10MB) to convert to Markdown-like text."),
    token: str = Depends(verify_token),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail="File too large (max 10MB)")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    parts.append(text)
            markdown = "\n\n".join(parts).strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not markdown:
        raise HTTPException(status_code=422, detail="No text extracted")
    return {"markdown": markdown}
