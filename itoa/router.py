from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from itoa.core import image_to_ascii
from enum import Enum
import io
import logging

router = APIRouter()


class AsciiMode(str, Enum):
    Standard = "Standard"
    Detailed = "Detailed"
    Blocks = "Blocks"
    Triangles = "Triangles"
    Simple = "Simple"
    Binary = "Binary"
    Minimal = "Minimal"
    Dots = "Dots"
    Circles = "Circles"
    Squares = "Squares"
    Shades = "Shades"
    Lines = "Lines"
    Slashes = "Slashes"
    Arrows = "Arrows"
    Box_Drawing = "Box Drawing"
    Brackets = "Brackets"
    Waves = "Waves"
    Stars = "Stars"
    Cards = "Cards"
    Music = "Music"
    Currency = "Currency"
    Math = "Math"
    Dingbats = "Dingbats"
    Braille = "Braille"
    Runes = "Runes"
    Greek = "Greek"
    Japanese = "Japanese"


@router.post("/convert")
async def convert_image_to_ascii(
    file: UploadFile = File(...),
    width: int = Form(
        100, ge=1, le=500,
        description="Width of the output ASCII art (1-500)"),
    color: bool = Form(
        False, description="Enable color output (ANSI escape codes)"),
    mode: AsciiMode = Form(
        AsciiMode.Standard, description="ASCII conversion mode")
):
    """
    Convert an uploaded image to ASCII art.
    """
    # A missing content-type is tolerated (some clients omit it); an explicit
    # non-image type is rejected.
    if file.content_type is not None and not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400, detail="File provided is not an image.")

    try:
        contents = await file.read()
        image_stream = io.BytesIO(contents)
        ascii_art = image_to_ascii(
            image_stream, width=width, color=color, mode=mode.value)
        return {"ascii": ascii_art}
    except ValueError:
        # image_to_ascii raises ValueError for undecodable input.
        raise HTTPException(status_code=400, detail="Invalid image file.")
    except Exception:
        logging.exception("itoa/convert failed")
        raise HTTPException(status_code=500, detail="Conversion failed.")
