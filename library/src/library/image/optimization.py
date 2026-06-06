from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

from PIL import Image

MEDIUM_WIDTH_SIZE = (1080, 0)
EXTRA_WIDTH_SIZE = (2560, 0)
EFFICIENT_BPP = 0.5
EXTRA_EFFICIENT_BPP = 0.2


class ImageFormat(StrEnum):
    PNG = "PNG"
    JPEG = "JPEG"
    GIF = "GIF"
    BMP = "BMP"
    WEBP = "WEBP"


class ImageMode(StrEnum):
    RGB = "RGB"
    RGBA = "RGBA"
    CMYK = "CMYK"
    L = "L"
    LA = "LA"
    I = "I"
    P = "P"
    ONE = "1"


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


def crop_image_dimensions(image: Image.Image, max_dimensions: tuple[int, int]) -> tuple[Image.Image, tuple[int, int]]:
    new_dimensions = crop_dimensions(image.size, max_dimensions=max_dimensions)
    if image.size != new_dimensions:
        return image.resize(new_dimensions, Image.Resampling.LANCZOS), new_dimensions
    return image, image.size


def discard_empty_alpha_channels_mode(image: Image.Image) -> tuple[Image.Image, bool]:
    """Allows to discard empty alpha channels from PNG"""
    if image.mode == "RGBA":
        extrema = image.getextrema()  # LOADS PIXEL DATA
        no_transparency = len(extrema) == 4 and extrema[3][0] == 255
        if no_transparency:
            return image.convert("RGB"), True
    return image, False


def get_image_header_info(image: Image.Image, filesize: int) -> dict:
    bpp = filesize / (image.width * image.height)
    is_animated = getattr(image, "is_animated", None)
    if is_animated:
        n_frames = getattr(image, "n_frames", None)

    result = {
        "filesize_kb": int(filesize / 1024),
        "size": image.size,
        "bpp": f"{bpp:.2f}",
        "format": image.format,
        "mode": image.mode,
        "is_animated": n_frames if is_animated else False,
    }
    return result


def get_image_transparency_info(image: Image.Image, filesize: int) -> dict:
    bpp = filesize / (image.width * image.height)
    is_animated = getattr(image, "is_animated", None)
    n_frames = getattr(image, "n_frames", None)
    has_transparency_data = image.has_transparency_data
    if has_transparency_data and image.format == ImageFormat.PNG:
        if useless_transparency_mode(image):
            has_transparency_data = "useless"

    result = {
        "original_filesize": f"{int(filesize / 1024)} Kb",
        "original_size": image.size,
        "bpp": f"{bpp:.2f}",
        "original_format": image.format,
        "original_mode": image.mode,
        "is_animated": n_frames if is_animated else False,
        "has_transparency_data": has_transparency_data,
    }
    return result


def useless_transparency_mode(image: Image.Image) -> bool:
    extrema = image.getextrema()
    return len(extrema) == 4 and extrema[3][0] == 255


def optimization_machine(image: Image.Image, buffer: BytesIO, filesize: int) -> dict:
    min_filesize = 50 * 1024
    result = {"success": True}
    if filesize < min_filesize:
        return result | {"error": f"Image is smaller then min threshold {filesize / 1024:.2fKB}"}

    bpp = filesize / (image.width * image.height)

    original_format = new_format = image.format
    result |= {"original_format": original_format}
    original_mode = new_mode = image.mode
    result |= {"original_mode": original_mode}
    original_size = image.size
    result |= {"original_size": original_size}
    result |= {"original_filesize": filesize}
    result |= {"bpp": bpp}

    efficient = bpp < EFFICIENT_BPP
    super_efficient = bpp < EXTRA_EFFICIENT_BPP

    if original_format == ImageFormat.PNG:
        is_animated = getattr(image, "is_animated", None)
        if is_animated:
            return result | {"error": f"Animated PNG (filesize={filesize}, bpp={bpp})"}

        if super_efficient:
            image, resized_size = crop_image_dimensions(image, EXTRA_WIDTH_SIZE)
        else:
            image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)
        if resized_size != original_size:
            result |= {"new_size": resized_size}

        if original_mode == ImageMode.RGBA:
            if useless_transparency_mode(image):
                new_mode = ImageMode.RGB
                image = image.convert(new_mode)
                result |= {"new_mode": new_mode}

        if not efficient and new_mode == ImageMode.RGB:
            new_format = ImageFormat.JPEG
            image.save(buffer, format=new_format, optimize=True, quality=85)
            return result | {"new_mode": new_mode, "new_filesize": len(buffer.getvalue())}
        if "new_size" not in result and "new_mode" not in result:
            return result | {"error": "Image was not optimized"}
        # Not processed 1, L, LA, I, P modes, need additional investigation
        image.save(buffer, format=new_format, optimize=True)
        return result

    if original_format == ImageFormat.JPEG:
        image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)
        if resized_size != original_size:
            result |= {"new_size": resized_size}
            image.save(buffer, format=ImageFormat.JPEG, optimize=True, quality=85)

        return result

    if original_format == ImageFormat.GIF:
        is_animated = getattr(image, "is_animated", None)
        if is_animated:
            return result | {"error": f"Animated GIF (filesize={filesize}, bpp={bpp})"}

        image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)
        if resized_size != original_size:
            image.save(buffer, format=ImageFormat.GIF, optimize=True, quality=85)
        return result

    return result | {"error": "Image was not optimized"}
