from dataclasses import replace
from io import BytesIO

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
from library.image.optimization import (
    crop_dimensions,
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


def needs_encoding(context: ImageProcessingContext) -> ImageSkipReason | None:
    current = context.current_image_info
    target = context.target_image_info
    if target.size != current.size or target.mode != current.mode or target.format != current.format:
        return None
    if current.format == ImageFormat.JPEG and (
        current.bytes_per_pixel >= BYTES_PER_PIXEL_05 or context.compression < 75
    ):
        return None
    return ImageSkipReason.NOT_OPTIMIZED


def select_encoding(context: ImageProcessingContext) -> None:
    if context.target_image_info.format == ImageFormat.JPEG:
        context.target_quality = 85 if context.original_image_info.format == ImageFormat.PNG else 75
    elif context.target_image_info.format == ImageFormat.GIF:
        context.target_quality = 85
    else:
        context.target_quality = None


def resize_image(context: ImageProcessingContext) -> None:
    if context.current_image_info.size != context.target_image_info.size:
        size = require(context.target_image_info.size, "Target image size")
        context.replace_image(context.image.resize(size, Image.Resampling.LANCZOS))


def convert_image(context: ImageProcessingContext) -> None:
    if context.current_image_info.mode != context.target_image_info.mode:
        context.replace_image(context.image.convert(context.target_image_info.mode))


def save_image(context: ImageProcessingContext) -> None:
    with BytesIO() as buffer:
        options = {} if context.target_quality is None else {"quality": context.target_quality}
        context.image.save(buffer, format=context.target_image_info.format, optimize=True, **options)
        context.candidate = buffer.getvalue()
    context.current_image_info = replace(
        context.current_image_info,
        format=context.target_image_info.format,
        filesize=len(context.candidate),
    )


def worthwhile_savings(context: ImageProcessingContext) -> ImageSkipReason | None:
    # Preserve the whole-percent cutoff: 97.9% counts as 97%.
    if int(context.current_image_info.filesize / context.preserved_image_info.filesize * 100) > 97:
        return ImageSkipReason.WORSE_CONVERSION
    return None


def accept_savings(context: ImageProcessingContext, step: str) -> None:
    context.image_info_history[step] = replace(context.current_image_info)
    if worthwhile_savings(context) is None:
        context.accept_image()
    else:
        context.restore_image()


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
        context.preserve_image()
        remove_useless_alpha(context)
        if convert_png_to_jpeg:
            convert_inefficient_png_to_jpeg(context)
        select_encoding(context)
        if needs_encoding(context) is None:
            convert_image(context)
            save_image(context)
            accept_savings(context, "conversion")
        else:
            context.restore_image()

        context.preserve_image()
        select_dimensions(context)
        if context.target_image_info.size != context.current_image_info.size:
            select_encoding(context)
            resize_image(context)
            save_image(context)
            accept_savings(context, "resize")
        else:
            context.restore_image()

        if context.candidate is None:
            if context.image_info_history:
                context.skip(
                    ImageSkipReason.WORSE_CONVERSION, new_image=next(reversed(context.image_info_history.values()))
                )
            context.skip(ImageSkipReason.NOT_OPTIMIZED)
        context.succeed()
    return context.outcome()
