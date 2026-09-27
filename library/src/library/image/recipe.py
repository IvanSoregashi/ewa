from dataclasses import replace
from io import BytesIO
from typing import cast

from PIL import Image

from library.image.constants import EXTRA_WIDTH_SIZE, MEDIUM_WIDTH_SIZE, ImageFormat, ImageMode
from library.image.context import ImageProcessingContext
from library.image.models import ImageOptimizationResult, ImageSkipReason
from library.image.optimization import (
    crop_image_dimensions,
    is_efficient,
    is_extra_efficient,
    useless_transparency_mode,
)


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


def resize_image(context: ImageProcessingContext) -> None:
    dimensions = context.max_dimensions
    if dimensions is None:
        info = context.original_image_info
        dimensions = MEDIUM_WIDTH_SIZE
        if info.format == ImageFormat.PNG and is_extra_efficient(info):
            dimensions = EXTRA_WIDTH_SIZE
        elif info.format == ImageFormat.JPEG:
            density = info.bytes_per_pixel
            if density is not None and density < 0.1:
                dimensions = EXTRA_WIDTH_SIZE
    resized, _ = crop_image_dimensions(context.image, dimensions)
    context.replace_image(resized)


def remove_useless_alpha(context: ImageProcessingContext) -> None:
    if (
        context.original_image_info.format == ImageFormat.PNG
        and context.image.mode == ImageMode.RGBA
        and useless_transparency_mode(context.image)
    ):
        context.replace_image(context.image.convert(ImageMode.RGB))


def convert_inefficient_png_to_jpeg(context: ImageProcessingContext) -> bool:
    if context.original_image_info.format != ImageFormat.PNG:
        return False
    info = replace(context.original_image_info, size=context.image.size, mode=ImageMode(context.image.mode))
    return not is_efficient(info) and info.mode == ImageMode.RGB


def png_to_jpeg(context: ImageProcessingContext) -> None:
    # The JPEG bytes are produced by save_image.
    context.output_format = ImageFormat.JPEG


def needs_encoding(context: ImageProcessingContext) -> ImageSkipReason | None:
    original = context.original_image_info
    if context.image.size != original.size or context.image.mode != original.mode or context.output_format != original.format:
        return None
    if original.format == ImageFormat.JPEG and (not is_efficient(original) or context.compression < 75):
        return None
    return ImageSkipReason.NOT_OPTIMIZED


def select_encoding(context: ImageProcessingContext) -> None:
    if context.output_format == ImageFormat.JPEG:
        context.output_quality = 85 if context.original_image_info.format == ImageFormat.PNG else 75
    elif context.output_format == ImageFormat.GIF:
        context.output_quality = 85
    else:
        context.output_quality = None


def save_image(context: ImageProcessingContext) -> None:
    with BytesIO() as buffer:
        options = {} if context.output_quality is None else {"quality": context.output_quality}
        context.image.save(buffer, format=context.output_format, optimize=True, **options)
        context.candidate = buffer.getvalue()
    context.new_image_info = replace(
        context.original_image_info,
        size=context.image.size,
        mode=ImageMode(context.image.mode),
        format=cast(ImageFormat, context.output_format),
        filesize=len(context.candidate),
    )


def worthwhile_savings(context: ImageProcessingContext) -> ImageSkipReason | None:
    # Preserve the whole-percent cutoff: 97.9% counts as 97%.
    if int(len(cast(bytes, context.candidate)) / context.original_image_info.filesize * 100) > 97:
        return ImageSkipReason.WORSE_CONVERSION
    return None


def optimize_image_with_context(
    content: bytes,
    *,
    compression: int = 100,
    convert_png_to_jpeg: bool = True,
    min_filesize: int = 50 * 1024,
    max_dimensions: tuple[int, int] | None = None,
) -> tuple[ImageOptimizationResult, bytes | None]:
    with ImageProcessingContext(
        compression=compression,
        min_filesize=min_filesize,
        max_dimensions=max_dimensions,
    ) as context:
        context.open_bytes_as_image(content)
        context.verify(minimum_filesize, supported_format, static_image)
        resize_image(context)
        remove_useless_alpha(context)
        if convert_png_to_jpeg and convert_inefficient_png_to_jpeg(context):
            png_to_jpeg(context)
        context.verify(needs_encoding)
        select_encoding(context)
        save_image(context)
        context.verify(worthwhile_savings)
        context.succeed()
    return context.outcome()
