from dataclasses import replace
from io import BytesIO

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
    assert context.image is not None
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
    image, _ = crop_image_dimensions(context.image, dimensions)
    context.replace_image(image)


def remove_useless_alpha(context: ImageProcessingContext) -> None:
    assert context.image is not None
    if (
        context.original_image_info.format == ImageFormat.PNG
        and context.image.mode == ImageMode.RGBA
        and useless_transparency_mode(context.image)
    ):
        context.replace_image(context.image.convert(ImageMode.RGB))


def encode_image(context: ImageProcessingContext) -> None:
    assert context.image is not None
    original = context.original_image_info
    info = replace(original, size=context.image.size, mode=ImageMode(context.image.mode))
    quality = None
    if original.format == ImageFormat.PNG:
        if context.convert_png_to_jpeg and not is_efficient(info) and info.mode == ImageMode.RGB:
            info.format = ImageFormat.JPEG
            quality = 85
        elif info == original:
            context.skip(ImageSkipReason.NOT_OPTIMIZED)
    elif original.format == ImageFormat.JPEG:
        if info.size == original.size and is_efficient(original) and context.compression >= 75:
            context.skip(ImageSkipReason.NOT_OPTIMIZED)
        quality = 75
    elif original.format == ImageFormat.GIF:
        if info.size == original.size:
            context.skip(ImageSkipReason.NOT_OPTIMIZED)
        quality = 85

    with BytesIO() as buffer:
        options = {} if quality is None else {"quality": quality}
        context.image.save(buffer, format=info.format, optimize=True, **options)
        context.candidate = buffer.getvalue()
    info.filesize = len(context.candidate)
    context.new_image_info = info


def worthwhile_savings(context: ImageProcessingContext) -> ImageSkipReason | None:
    assert context.candidate is not None
    # Preserve the whole-percent cutoff: 97.9% counts as 97%.
    if int(len(context.candidate) / context.original_image_info.filesize * 100) > 97:
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
        convert_png_to_jpeg=convert_png_to_jpeg,
        min_filesize=min_filesize,
        max_dimensions=max_dimensions,
    ) as context:
        context.open_bytes_as_image(content)
        context.verify(minimum_filesize, supported_format, static_image)
        resize_image(context)
        remove_useless_alpha(context)
        encode_image(context)
        context.verify(worthwhile_savings)
        context.succeed()
    return context.outcome()
