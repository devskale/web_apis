import requests
from pathlib import Path
import sys


def test_image(image_path, port=8002, color=False):
    # Try with /api prefix first as per user example, then fallback to /itoa/convert
    paths = ["/api/itoa/convert", "/itoa/convert"]

    # Refactored retry logic
    success = False
    for path in paths:
        url = f"http://127.0.0.1:{port}{path}"
        print(f"Attempting URL: {url}")
        try:
            with open(image_path, 'rb') as f:
                files = {'file': f}
                data = {'width': 80, 'color': color}
                response = requests.post(url, files=files, data=data)

            if response.status_code == 200:
                result = response.json()
                ascii_art = result.get('ascii')
                print("-" * 40)
                print(ascii_art)
                print("-" * 40)
                print(f"Successfully converted {image_path.name}")
                success = True
                break  # Stop trying other paths
            elif response.status_code == 404:
                print(f"404 Not Found at {url}, trying next path...")
                continue
            else:
                print(f"Error: {response.status_code} - {response.text}")
                break  # Server reachable but error, don't retry path
        except requests.exceptions.ConnectionError:
            print(f"Connection refused at {url}")
            # If connection refused, likely server not running or wrong port.
            # Trying another path on same port won't help if port is closed.
            # But maybe we should just report it.
            # continue
        except Exception as e:
            print(f"Failed to request: {e}")
            break

    if not success:
        print("Could not convert image.")


def main():
    data_dir = Path("data")
    if not data_dir.exists():
        print("Data directory not found.")
        return

    # Test with a few images
    images = list(data_dir.glob("*.jpg")) + list(data_dir.glob("*.jpeg"))

    if not images:
        print("No images found in data/ directory.")
        return

    # Sort by size to pick smaller/simpler ones first or just take the first few
    images.sort(key=lambda x: x.name)

    # Test 'amiga.jpg' specifically if it exists, otherwise the first one
    amiga = next((img for img in images if 'amiga.jpg' in img.name), None)

    if amiga:
        test_image(amiga, color=False)
        test_image(amiga, color=True)
    elif images:
        test_image(images[0], color=False)
        test_image(images[0], color=True)

    # Optional: Test another one if available
    if len(images) > 1 and images[1] != amiga:
        test_image(images[1], color=False)


if __name__ == "__main__":
    main()
