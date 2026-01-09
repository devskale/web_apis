from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from itoa.core import image_to_ascii
import io

router = APIRouter()


@router.post("/convert")
async def convert_image_to_ascii(
    file: UploadFile = File(...),
    width: int = Form(100, description="Width of the output ASCII art"),
    color: bool = Form(
        False, description="Enable color output (ANSI escape codes)")
):
    """
    Convert an uploaded image to ASCII art.
    """
    if file.content_type is None or not file.content_type.startswith("image/"):
        # If content type is missing, we might want to allow it or check extension.
        # For now, let's just log it and be lenient if it's missing, or strict.
        # The error was AttributeError: 'NoneType' object has no attribute 'startswith'
        # implying file.content_type was None.
        if file.content_type is None:
            pass  # Or check filename extension?
        else:
            raise HTTPException(
                status_code=400, detail="File provided is not an image.")

    try:
        contents = await file.read()
        image_stream = io.BytesIO(contents)
        ascii_art = image_to_ascii(image_stream, width=width, color=color)
        return {"ascii": ascii_art}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
