from PIL import Image

from library.asserts import require
from library.image.constants import (
    EXTRA_WIDTH_SIZE,
    MEDIUM_WIDTH_SIZE,
    ImageFormat,
    ImageMode,
    BYTES_PER_PIXEL_01,
    BYTES_PER_PIXEL_02,
    BYTES_PER_PIXEL_05,
)
from library.image.context import ImageProcessingContext
from library.image.models import ImageOptimizationResult, ImageSkipReason
from library.image.utils import useless_transparency_mode, crop_dimensions


def minimum_filesize(context: ImageProcessingContext) -> ImageSkipReason | None:
    if context.original_image_info.filesize < context.min_filesize:
        return ImageSkipReason.SMALL_IMAGE
    return None


def supported_format(context: ImageProcessingContext) -> ImageSkipReason | None:
    if context.original_image_info.format not in (ImageFormat.PNG, ImageFormat.JPEG, ImageFormat.GIF):
        return ImageSkipReason.NOT_OPTIMIZED
    return None


def static_image(context: ImageProcessingContext) -> ImageSkipReason | None:
    info = context.original_image_info
    if info.format in (ImageFormat.PNG, ImageFormat.GIF) and info.is_animated:
        return ImageSkipReason.HAS_ANIMATION
    return None


def select_dimensions(context: ImageProcessingContext) -> None:
    dimensions = context.max_dimensions
    info = context.current_image_info
    if dimensions is None:
        match info.format:
            case ImageFormat.PNG if info.bytes_per_pixel < BYTES_PER_PIXEL_02:
                dimensions = EXTRA_WIDTH_SIZE
            case ImageFormat.JPEG if info.bytes_per_pixel < BYTES_PER_PIXEL_01:
                dimensions = EXTRA_WIDTH_SIZE
            case _:
                dimensions = MEDIUM_WIDTH_SIZE
    context.target_image_info.size = crop_dimensions(require(info.size, "Current image size"), dimensions)


def remove_useless_alpha(context: ImageProcessingContext) -> None:
    if (
        context.current_image_info.format == ImageFormat.PNG
        and context.current_image_info.mode == ImageMode.RGBA
        and useless_transparency_mode(context.image)
    ):
        context.target_image_info.mode = ImageMode.RGB


def convert_inefficient_png_to_jpeg(context: ImageProcessingContext) -> None:
    info = context.current_image_info
    if (
        info.format == ImageFormat.PNG
        and context.target_image_info.mode == ImageMode.RGB
        and info.bytes_per_pixel >= BYTES_PER_PIXEL_05
    ):
        context.target_image_info.format = ImageFormat.JPEG


def recompress_jpeg(context: ImageProcessingContext) -> None:
    info = context.current_image_info
    if info.format == ImageFormat.JPEG and (info.bytes_per_pixel >= BYTES_PER_PIXEL_05 or context.compression < 75):
        context.replace_image(context.image)


def select_encoding(context: ImageProcessingContext) -> None:
    if context.target_image_info.format == ImageFormat.JPEG:
        context.target_quality = 85 if context.original_image_info.format == ImageFormat.PNG else 75
    elif context.target_image_info.format == ImageFormat.GIF:
        context.target_quality = 85
    else:
        context.target_quality = None


def resize_image(context: ImageProcessingContext) -> None:
    new_size = require(context.target_image_info.size, "Target image size")
    if context.current_image_info.size != new_size:
        context.replace_image(context.image.resize(new_size, Image.Resampling.LANCZOS))


def convert_image(context: ImageProcessingContext) -> None:
    current = context.current_image_info
    target = context.target_image_info
    if current.mode == target.mode and current.format == target.format:
        return

    image = context.image
    if current.mode != target.mode:
        image = image.convert(mode=target.mode)
    context.replace_image(image)


def optimize_image(
    content: bytes,
    *,
    compression: int = 100,
    convert_png_to_jpeg: bool = True,
    min_filesize: int = 50 * 1024,
    max_dimensions: tuple[int, int] | None = None,
) -> tuple[ImageOptimizationResult, bytes | None]:
    """Return accepted bytes, or None for a skip/error; never mutate the input.

    max_dimensions=None uses density-based limits; (0, 0) disables resizing.
    A zero width or height leaves that axis unconstrained. min_filesize is in bytes.
    """
    with ImageProcessingContext(
        compression=compression,
        min_filesize=min_filesize,
        max_dimensions=max_dimensions,
    ) as context:
        context.open_bytes_as_image(content)
        context.verify(minimum_filesize, supported_format, static_image)
        remove_useless_alpha(context)
        if convert_png_to_jpeg:
            convert_inefficient_png_to_jpeg(context)
        select_encoding(context)
        recompress_jpeg(context)
        convert_image(context)
        select_dimensions(context)
        select_encoding(context)
        resize_image(context)
    return context.outcome()
