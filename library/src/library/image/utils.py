import math
from pathlib import Path

from PIL import Image


def calculate_bpp(size: int, width: int, height: int) -> float:
    return float(size) / (float(width) * float(height))

def calculate_image_bpp(image: Image.Image, size: int) -> float:
    return calculate_bpp(size, image.width, image.height)

def calculate_image_file_bpp(path: Path) -> float:
    file_size = path.stat().st_size
    with Image.open(path) as image:
        return calculate_image_bpp(image, file_size)