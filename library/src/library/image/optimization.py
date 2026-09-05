import io
import logging
from copy import deepcopy
from io import BytesIO

from PIL import Image

from library.image.constants import (
    MEDIUM_WIDTH_SIZE,
    EXTRA_WIDTH_SIZE,
    ANIMATION_CRF,
    ANIMATION_SIZE_LIMIT,
    ImageFormat,
    ImageMode,
    USELESS_ALPHA_THRESHOLD,
)
from library.image.models import (
    ImageErrorReason,
    ImageInfo,
    ImageOptimizationResult,
    ImageSkipReason,
)
from library.image.optimize_gif import convert_to_mp4

logger = logging.getLogger(__name__)


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
        no_transparency = len(extrema) == 4 and extrema[3][0] >= USELESS_ALPHA_THRESHOLD
        if no_transparency:
            return image.convert("RGB"), True
    return image, False


def useless_transparency_mode(image: Image.Image) -> bool:
    extrema = image.getextrema()
    return len(extrema) == 4 and extrema[3][0] >= USELESS_ALPHA_THRESHOLD


def optimize_png_image(image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo, filesize: int, compression: int) -> ImageOptimizationResult:
    image_info = deepcopy(original_image_info)

    if original_image_info.is_animated:
        return ImageOptimizationResult(skip=ImageSkipReason.HAS_ANIMATION, original_image=original_image_info)

    # Reduce the image dimensions
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
        new_size = len(buffer.getvalue())
        if new_size < filesize:
            image_info.filesize = new_size
            return ImageOptimizationResult(success=True, original_image=original_image_info, new_image=image_info)

    #  Not processed 1, L, LA, I, P modes, need additional investigation
    if original_image_info == image_info and compression > 96:
        return ImageOptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)

    image.save(buffer, format=image_info.format, optimize=True)
    return ImageOptimizationResult(success=True, original_image=original_image_info, new_image=image_info)


def optimize_jpg_image(image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo, filesize: int, compression: int) -> ImageOptimizationResult:
    image_info = deepcopy(original_image_info)
    if original_image_info.bpp < 0.1:
        image, image_info.size = crop_image_dimensions(image, EXTRA_WIDTH_SIZE)
    else:
        image, image_info.size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)

    #  Image was resized
    if image_info.size != original_image_info.size or compression < 96:
        jpg_buffer = io.BytesIO()
        image.save(jpg_buffer, format=ImageFormat.JPEG, optimize=True, quality=85)
        png_buffer = io.BytesIO()
        image.save(png_buffer, format=ImageFormat.PNG, optimize=True)
        new_size_jpg = len(jpg_buffer.getvalue())
        new_size_png = len(png_buffer.getvalue())

        if new_size_jpg < new_size_png and new_size_jpg < filesize:
            image_info.filesize = new_size_jpg
            buffer.write(jpg_buffer.getbuffer())
            return ImageOptimizationResult(success=True, original_image=original_image_info, new_image=image_info)

        if new_size_png < filesize:
            image_info.filesize = new_size_png
            image_info.format = ImageFormat.PNG
            buffer.write(png_buffer.getbuffer())
            return ImageOptimizationResult(success=True, original_image=original_image_info, new_image=image_info)

    return ImageOptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)


def convert_animation_to_mp4(
    image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo
) -> ImageOptimizationResult:
    """Transcode an oversized animation to MP4 (h264, crf 30) via system ffmpeg.

    Device-validated markup standard (see recipe_html.replace_gifs_with_videos):
    Moon+ and BOOX play videos bound by the `src` attribute; posters and previews
    are handled at the recipe layer (same-basename JPEG + <img> fallback).

    The result carries ImageFormat.MP4 so the caller can rename the resource
    (.gif -> .mp4). On ffmpeg absence/failure the animation is skipped (kept
    as GIF).
    """
    mp4_bytes, info = convert_to_mp4(image, original_image_info.filesize, crf=ANIMATION_CRF)
    if mp4_bytes is None:
        logger.warning(f"animation conversion skipped: {info}")
        return ImageOptimizationResult(skip=ImageSkipReason.HAS_ANIMATION, original_image=original_image_info)

    image_info = deepcopy(original_image_info)
    image_info.format = ImageFormat.MP4
    image_info.filesize = len(mp4_bytes)
    buffer.write(mp4_bytes)
    return ImageOptimizationResult(success=True, original_image=original_image_info, new_image=image_info)


def optimize_gif_image(image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo, filesize: int, compression: int) -> ImageOptimizationResult:
    image_info = deepcopy(original_image_info)

    if original_image_info.is_animated:
        # if original_image_info.filesize > ANIMATION_SIZE_LIMIT:
        #     return convert_animation_to_mp4(image, buffer, original_image_info)
        return ImageOptimizationResult(skip=ImageSkipReason.HAS_ANIMATION, original_image=original_image_info)

    image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)

    if resized_size != image_info.size:
        image_info.size = resized_size
        image.save(buffer, format=ImageFormat.GIF, optimize=True, quality=85)
        return ImageOptimizationResult(success=True, original_image=original_image_info, new_image=image_info)

    return ImageOptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)


def optimization_machine(image: Image.Image, buffer: BytesIO, filesize: int, compression: int) -> ImageOptimizationResult:
    """Single failure net: any pixel-decoding/encoding failure on a broken or
    exotic image becomes an error result instead of an exception."""
    min_filesize = 50 * 1024
    original_image_info = ImageInfo.from_image(image=image, filesize=filesize)

    try:
        if filesize < min_filesize:
            return ImageOptimizationResult(skip=ImageSkipReason.SMALL_IMAGE, original_image=original_image_info)

        if original_image_info.format == ImageFormat.PNG:
            return optimize_png_image(image, buffer, original_image_info, filesize, compression)

        if original_image_info.format == ImageFormat.JPEG:
            return optimize_jpg_image(image, buffer, original_image_info, filesize, compression)

        if original_image_info.format == ImageFormat.GIF:
            return optimize_gif_image(image, buffer, original_image_info, filesize, compression)

        return ImageOptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)


    except Exception as e:
        reason = ImageErrorReason.from_error(e)
        logger.warning(f"optimization failed ({reason.name}): {e}")
        return ImageOptimizationResult(error=reason, original_image=original_image_info)
