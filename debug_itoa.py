from itoa.core import image_to_ascii
from pathlib import Path
import io

def debug():
    image_path = Path("data/amiga.jpg")
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return

    print(f"Processing {image_path}...")
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
            
        stream = io.BytesIO(image_data)
        result = image_to_ascii(stream, width=80)
        print("Success!")
        print(result[:100] + "...") # Print start of result
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug()
