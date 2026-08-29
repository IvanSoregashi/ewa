import logging
from copy import deepcopy
from io import BytesIO

from PIL import Image

from library.image.constants import (
    MEDIUM_WIDTH_SIZE,
    EXTRA_WIDTH_SIZE,
    ImageFormat,
    ImageMode,
)
from library.image.models import (
    ImageErrorReason,
    ImageInfo,
    OptimizationResult,
    ImageSkipReason,
)

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
        no_transparency = len(extrema) == 4 and extrema[3][0] == 255
        if no_transparency:
            return image.convert("RGB"), True
    return image, False


def useless_transparency_mode(image: Image.Image) -> bool:
    extrema = image.getextrema()
    return len(extrema) == 4 and extrema[3][0] == 255


def optimize_png_image(image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo) -> OptimizationResult:
    image_info = deepcopy(original_image_info)

    if original_image_info.is_animated:
        return OptimizationResult(skip=ImageSkipReason.HAS_ANIMATION, original_image=original_image_info)

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
        image_info.filesize = len(buffer.getvalue())
        return OptimizationResult(success=True, original_image=original_image_info, new_image=image_info)

    #  Not processed 1, L, LA, I, P modes, need additional investigation
    if original_image_info == image_info:
        return OptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)

    image.save(buffer, format=image_info.format, optimize=True)
    return OptimizationResult(success=True, original_image=original_image_info, new_image=image_info)


def optimize_jpg_image(image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo) -> OptimizationResult:
    image_info = deepcopy(original_image_info)
    image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)

    #  Image was resized
    if resized_size != image_info.size:
        image_info.size = resized_size
        image.save(buffer, format=ImageFormat.JPEG, optimize=True, quality=85)
        image_info.filesize = len(buffer.getvalue())
        return OptimizationResult(success=True, original_image=original_image_info, new_image=image_info)

    return OptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)


def optimize_gif_image(image: Image.Image, buffer: BytesIO, original_image_info: ImageInfo) -> OptimizationResult:
    image_info = deepcopy(original_image_info)

    if original_image_info.is_animated:
        return OptimizationResult(skip=ImageSkipReason.HAS_ANIMATION, original_image=original_image_info)

    image, resized_size = crop_image_dimensions(image, MEDIUM_WIDTH_SIZE)

    if resized_size != image_info.size:
        image_info.size = resized_size
        image.save(buffer, format=ImageFormat.GIF, optimize=True, quality=85)
        return OptimizationResult(success=True, original_image=original_image_info, new_image=image_info)

    return OptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)


def classify_error(e: Exception) -> ImageErrorReason:
    """Best-effort classification of the single-net exception.

    Type checks are reliable; decode-vs-encode relies on Pillow's stable
    message fragments, since exception types overlap between the two stages.
    """
    if isinstance(e, (Image.DecompressionBombError, MemoryError)):
        return ImageErrorReason.TOO_LARGE

    message = str(e).lower()
    if any(fragment in message for fragment in ("truncated", "broken", "cannot identify", "tile cannot extend")):
        return ImageErrorReason.DECODE_FAILED
    if any(fragment in message for fragment in ("cannot write mode", "cannot save", "encoder")):
        return ImageErrorReason.ENCODE_FAILED

    return ImageErrorReason.UNKNOWN


def optimization_machine(image: Image.Image, buffer: BytesIO, filesize: int) -> OptimizationResult:
    """Single failure net: any pixel-decoding/encoding failure on a broken or
    exotic image becomes an error result instead of an exception."""
    min_filesize = 50 * 1024
    original_image_info = ImageInfo.from_image(image=image, filesize=filesize)

    try:
        if filesize < min_filesize:
            return OptimizationResult(skip=ImageSkipReason.SMALL_IMAGE, original_image=original_image_info)

        if original_image_info.format == ImageFormat.PNG:
            return optimize_png_image(image, buffer, original_image_info)

        if original_image_info.format == ImageFormat.JPEG:
            return optimize_jpg_image(image, buffer, original_image_info)

        if original_image_info.format == ImageFormat.GIF:
            return optimize_gif_image(image, buffer, original_image_info)

        return OptimizationResult(skip=ImageSkipReason.NOT_OPTIMIZED, original_image=original_image_info)

    except Exception as e:
        logger.warning(f"optimization failed ({classify_error(e)}): {e}")
        return OptimizationResult(error=classify_error(e), original_image=original_image_info)
