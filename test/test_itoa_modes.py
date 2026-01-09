import requests
from PIL import Image
import io
import time

BASE_URL = "http://localhost:8002/itoa/convert"


def create_dummy_image():
    # Create a gradient image to test different characters
    width, height = 100, 100
    img = Image.new('RGB', (width, height))
    pixels = []
    for y in range(height):
        for x in range(width):
            val = int((x / width) * 255)
            pixels.append((val, val, val))
    img.putdata(pixels)

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr


def test_convert_modes():
    modes = [
        "Standard", "Detailed", "Blocks", "Triangles", "Simple", "Binary",
        "Minimal", "Dots", "Circles", "Squares", "Shades", "Lines",
        "Slashes", "Arrows", "Box Drawing", "Brackets", "Waves", "Stars",
        "Cards", "Music", "Currency", "Math", "Dingbats", "Braille",
        "Runes", "Greek", "Japanese"
    ]

    print(f"Testing {len(modes)} modes against {BASE_URL}")

    for mode in modes:
        print(f"Testing mode: {mode}...", end=" ", flush=True)
        try:
            img = create_dummy_image()
            files = {'file': ('test.png', img, 'image/png')}
            data = {'width': 50, 'mode': mode}
            response = requests.post(BASE_URL, files=files, data=data)

            if response.status_code == 200:
                result = response.json()
                if 'ascii' in result and len(result['ascii']) > 0:
                    print("OK")
                else:
                    print(f"FAILED (Invalid response format): {result}")
            else:
                print(
                    f"FAILED (Status {response.status_code}): {response.text}")

        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    # Wait for server to be ready?
    # The user says "running continuously", so we assume it is up or we start it.
    # For this script, we just run the tests.
    test_convert_modes()
