from pathlib import Path

from PIL import Image

from library.image.constants import USELESS_ALPHA_THRESHOLD


def crop_dimensions(image_dimensions: tuple[int, int], max_dimensions: tuple[int, int]) -> tuple[int, int]:
    width, height = image_dimensions
    max_width, max_height = max_dimensions

    new_width, new_height = width, height
    if max_width and width > max_width:
        ratio = max_width / new_width
        new_width = max_width
        new_height = max(1, int(new_height * ratio))

    if max_height and new_height > max_height:
        ratio = max_height / new_height
        new_width = max(1, int(new_width * ratio))
        new_height = max_height

    return new_width, new_height


def useless_transparency_mode(image: Image.Image) -> bool:
    extrema = image.getextrema()
    return len(extrema) == 4 and extrema[3][0] >= USELESS_ALPHA_THRESHOLD


def calculate_bpp(size: int, width: int, height: int) -> float:
    return float(size) / (float(width) * float(height))


def calculate_image_bpp(image: Image.Image, size: int) -> float:
    return calculate_bpp(size, image.width, image.height)


def calculate_image_file_bpp(path: Path) -> float:
    file_size = path.stat().st_size
    with Image.open(path) as image:
        return calculate_image_bpp(image, file_size)
