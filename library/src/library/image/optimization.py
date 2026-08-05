from copy import copy, deepcopy
from io import BytesIO

from PIL import Image

from library.image.constants import (
    MEDIUM_WIDTH_SIZE,
    EXTRA_WIDTH_SIZE,
    EFFICIENT_BPP,
    EXTRA_EFFICIENT_BPP,
    ImageFormat,
    ImageMode,
)
from library.image.models import ConversionSettings, ImageInfo, OperationResult

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


def optimize_png_image(
    image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo
) -> tuple[OperationResult, ImageInfo | None]:
    image_info = deepcopy(original_image_info)

    if getattr(image, "is_animated", None):
        return OperationResult(skip=f"Animated PNG"), None

    #  Reduce the image dimensions
    if image_info.is_extra_efficient:
        image, resized_size = crop_image_dimensions(image, EXTRA_WIDTH_SIZE)
    else:
        image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)
    image_info.size = resized_size

    #  Remove transparency if it is useless
    if image_info.mode == ImageMode.RGBA and useless_transparency_mode(image):
        image = image.convert(ImageMode.RGB)
        image_info.mode = ImageMode.RGB

    #  Convert to JPG if meaningful
    if not image_info.is_efficient and image_info.mode == ImageMode.RGB:
        image_info.format = ImageFormat.JPEG
        image.save(buffer, format=ImageFormat.JPEG, optimize=True, quality=85)
        image_info.filesize = len(buffer.getvalue())
        return OperationResult(success=True), image_info

    #  Not processed 1, L, LA, I, P modes, need additional investigation
    if original_image_info == image_info:
        return OperationResult(skip="Image was not optimized"), None

    image.save(buffer, format=image_info.format, optimize=True)
    return OperationResult(success=True), image_info


def optimize_jpg_image(
    image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo
) -> tuple[OperationResult, ImageInfo | None]:
    image_info = deepcopy(original_image_info)
    image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)

    #  Image was resized
    if resized_size != image_info.size:
        image_info.size = resized_size
        image.save(buffer, format=ImageFormat.JPEG, optimize=True, quality=85)
        return OperationResult(success=True), image_info

    return OperationResult(skip="Image was not optimized"), None


def optimize_gif_image(
    image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo
) -> tuple[OperationResult, ImageInfo | None]:
    image_info = deepcopy(original_image_info)

    if getattr(image, "is_animated", None):
        return OperationResult(skip="Animated GIF"), None

    image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)

    if resized_size != image_info.size:
        image_info.size = resized_size
        image.save(buffer, format=ImageFormat.GIF, optimize=True, quality=85)
        return OperationResult(success=True), image_info

    return OperationResult(skip="Image was not optimized"), None


def optimization_machine(
    image: Image.Image, buffer: BytesIO, filesize: int
) -> tuple[OperationResult, ImageInfo | None]:
    min_filesize = 50 * 1024
    if filesize < min_filesize:
        return OperationResult(skip=f"Image is smaller then min threshold {filesize / 1024:.2fKB}"), None

    image_info = ImageInfo.from_image(image=image, filesize=filesize)

    if image_info.format == ImageFormat.PNG:
        return optimize_png_image(image, buffer, image_info)

    if image_info.format == ImageFormat.JPEG:
        return optimize_jpg_image(image, buffer, image_info)

    if image_info.format == ImageFormat.GIF:
        return optimize_gif_image(image, buffer, image_info)

    return OperationResult(skip="Image was not optimized"), None
