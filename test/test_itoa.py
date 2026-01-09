from itoa.core import image_to_ascii
from PIL import Image
import io

def test_image_to_ascii():
    # Create a simple 10x10 gradient image
    img = Image.new('RGB', (10, 10))
    pixels = []
    for y in range(10):
        for x in range(10):
            # Gradient from black to white
            val = int((x + y) / 18 * 255)
            pixels.append((val, val, val))
    img.putdata(pixels)
    
    # Save to bytes
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    ascii_art = image_to_ascii(buf, width=10)
    print("ASCII Art Output:")
    print(ascii_art)
    
    assert len(ascii_art) > 0
    assert "\n" in ascii_art

if __name__ == "__main__":
    test_image_to_ascii()
