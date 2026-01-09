import sys
import os

# Add project root to path so we can import itoa
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import glob
import io
from PIL import Image
from itoa.core import image_to_ascii


def test_image_to_ascii_from_data():
    # Define data directory
    data_dir = os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))), 'data')

    # Get all image files
    image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(data_dir, ext)))

    if not image_files:
        print(f"No image files found in {data_dir}. Skipping data tests.")
        # Fallback to creating a simple image for test stability if data is empty
        print("Running fallback synthetic test...")
        test_image_to_ascii_synthetic()
        return

    print(f"Found {len(image_files)} images in {data_dir}")

    # Palettes to demonstrate
    palettes = ["Standard", "Blocks", "Binary", "Simple", "Dots", "Japanese"]

    for img_path in image_files:
        print(f"\n{'='*50}")
        print(f"Testing Image: {os.path.basename(img_path)}")
        print(f"{'='*50}")

        for mode in palettes:
            print(f"\n--- Mode: {mode} (Monochrome) ---")
            try:
                # Test with path, using a width that fits in most terminals
                ascii_art = image_to_ascii(
                    img_path, width=60, mode=mode, color=False)
                print(ascii_art)

                # Check for absence of ANSI codes in monochrome
                if '\x1b[' in ascii_art:
                    print("ERROR: Found ANSI escape codes in monochrome output!")
                else:
                    print("Verified: No ANSI codes in monochrome output.")

            except Exception as e:
                print(f"FAILED to convert in mode {mode}: {e}")

            print(f"\n--- Mode: {mode} (Color) ---")
            try:
                # Test with path, using a width that fits in most terminals
                ascii_art_color = image_to_ascii(
                    img_path, width=60, mode=mode, color=True)
                print(ascii_art_color)

                # Check for presence of ANSI codes in color
                if '\x1b[' in ascii_art_color:
                    print("Verified: Found ANSI escape codes in color output.")
                else:
                    print("ERROR: No ANSI escape codes found in color output!")

            except Exception as e:
                print(f"FAILED to convert in mode {mode} (Color): {e}")


def test_image_to_ascii_synthetic():
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
    # print("ASCII Art Output:")
    # print(ascii_art)

    assert len(ascii_art) > 0
    assert "\n" in ascii_art


if __name__ == "__main__":
    test_image_to_ascii_from_data()
