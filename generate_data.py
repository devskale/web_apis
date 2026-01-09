from PIL import Image, ImageDraw


def create_sample_image(filename):
    img = Image.new('RGB', (200, 200), color=(73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10, 10), "Hello World", fill=(255, 255, 0))
    d.rectangle([50, 50, 150, 150], outline="red", width=3)
    d.line([0, 0, 200, 200], fill="green", width=3)
    d.line([0, 200, 200, 0], fill="green", width=3)
    img.save(filename)


if __name__ == "__main__":
    create_sample_image("data/sample_1.png")

    # Create another one with gradient
    img2 = Image.new('RGB', (100, 100))
    pixels = []
    for y in range(100):
        for x in range(100):
            pixels.append((x * 2, y * 2, 100))
    img2.putdata(pixels)
    img2.save("data/sample_gradient.png")
