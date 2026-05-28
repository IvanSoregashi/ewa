from dataclasses import dataclass

from PIL import Image


@dataclass
class ConversionSettings:
    max_width: int
    max_height: int
    convert_rgb_to_jpg: bool
    quality: int | None


epub_image_settings = ConversionSettings(max_width=1080, max_height=0, convert_rgb_to_jpg=True, quality=80)


def crop_dimensions(image_dimensions: tuple[int, int], max_dimensions: tuple[int, int]) -> tuple[int, int]:
    width, height = image_dimensions
    max_width, max_height = max_dimensions

    new_width, new_height = width, height
    if max_width and width > max_width:
        ratio = max_width / width
        new_width = max_width
        new_height = int(height * ratio)

    if max_height and new_height > max_height:
        ratio = max_height / new_height
        new_width = int(width * ratio)
        new_height = max_height

    return new_width, new_height


def crop_image_dimensions(image: Image.Image, settings: ConversionSettings) -> tuple[Image.Image, bool]:
    new_dimensions = crop_dimensions(image.size, (settings.max_width, settings.max_height))
    if image.size != new_dimensions:
        return image.resize(new_dimensions, Image.Resampling.LANCZOS), True
    return image, False


def discard_empty_alpha_channels_mode(image: Image.Image) -> tuple[Image.Image, bool]:
    """Allows to discard empty alpha channels from PNG"""
    if image.mode == "RGBA":
        extrema = image.getextrema()  # LOADS PIXEL DATA
        no_transparency = len(extrema) == 4 and extrema[3][0] == 255
        new_mode = "RGB" if no_transparency else "RGBA"
        return image.convert(new_mode), True
    return image, False


def optimize_epub_image(image: Image.Image) -> tuple[Image.Image, bool]:
    image, resized = crop_image_dimensions(image, epub_image_settings)
    image, converted = discard_empty_alpha_channels_mode(image)
    return image, resized or converted
