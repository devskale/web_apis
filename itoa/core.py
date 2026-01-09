from PIL import Image
import math

# Charset from https://github.com/solst-ice/itoa
# ".:-=+*#%@" (from darkest to brightest)
ASCII_PALETTES = {
    "Standard": " .:-=+*#%@",
    "Detailed": " .'\"`,^:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
    "Blocks": " ░▒▓█",
    "Triangles": " ◺◹◸◿▸▹►▻▷▶",
    "Simple": " .-+*#@",
    "Binary": "01",
    "Minimal": " .@",
    "Dots": " .·•●",
    "Circles": " ○◌◍◐◑●",
    "Squares": " ▫▪◽◾◻◼",
    "Shades": " ░▒▓█",
    "Lines": " -=≡",
    "Slashes": " /\\|",
    "Arrows": " ←↑→↓",
    "Box Drawing": " ─│┼╬█",
    "Brackets": " ()[]{}",
    "Waves": " ∼≈≋",
    "Stars": " .·*✦✧★",
    "Cards": " ♤♡♢♧",
    "Music": " ♪♫♬",
    "Currency": " ¢$€£¥",
    "Math": " ∙·+×÷",
    "Dingbats": " ○◇◊◆",
    "Braille": " ⠁⠃⠇⠏⠟⠿⣿",
    "Runes": " ᚁᚂᚃᚄᚅᚆᚇᚈ",
    "Greek": " αβγδεζηθ",
    "Japanese": " 。あいうえおかきくけこ",
}


def image_to_ascii(image_file, width=100, color=False, mode="Standard"):
    """
    Converts an image file to ASCII art.

    Args:
        image_file: The image file object (bytes or path).
        width: The desired width of the output ASCII.
        color: Whether to return colorized HTML (not implemented yet, returns monochrome).
        mode: The ASCII character palette to use.

    Returns:
        str: The ASCII art string.
    """
    try:
        img = Image.open(image_file)
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}")

    # Calculate height to maintain aspect ratio
    # Adjusting for font aspect ratio (approx 0.55 for Courier/Monospace)
    if img.width <= 0 or img.height <= 0:
        raise ValueError("Image dimensions must be positive")

    aspect_ratio = img.height / img.width
    height = int(width * aspect_ratio * 0.55)

    # Ensure height and width are at least 1
    height = max(1, height)
    if width < 1:
        width = 1

    img = img.resize((width, height))
    img = img.convert("RGB")

    pixels = list(img.getdata())
    ascii_img = ""
    
    chars = ASCII_PALETTES.get(mode, ASCII_PALETTES["Standard"])

    col_count = 0

    for pixel in pixels:
        # Check if pixel is int (grayscale) or tuple (RGB)
        if isinstance(pixel, int):
            r = g = b = pixel
        elif len(pixel) >= 3:
            r, g, b = pixel[:3]
        else:
            r = g = b = 0

        # Luminance formula: 0.299R + 0.587G + 0.114B
        brightness = (0.299 * r + 0.587 * g + 0.114 * b)

        # Map brightness to index
        index = int((brightness / 255) * (len(chars) - 1))
        index = max(0, min(index, len(chars) - 1))

        char = chars[index]

        if color:
            # ANSI TrueColor: \x1b[38;2;R;G;Bm
            ascii_img += f"\x1b[38;2;{r};{g};{b}m{char}\x1b[0m"
        else:
            ascii_img += char

        col_count += 1
        if col_count >= width:
            ascii_img += "\n"
            col_count = 0

    return ascii_img
