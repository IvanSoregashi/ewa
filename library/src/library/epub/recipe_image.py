import io
import logging
import zipfile
from pathlib import PurePosixPath

from library.epub.resources import Resource
from PIL import Image

from library.image.constants import ImageMode, ImageFormat
from library.image.models import ImageErrorReason, ImageInfo, OptimizationResult
from library.image.optimization import classify_error, optimization_machine

logger = logging.getLogger(__name__)


def _classify_recipe_error(e: Exception) -> ImageErrorReason:
    """Classification for failures that happen before optimization_machine.

    Note: UnidentifiedImageError subclasses OSError, so it must be tested first.
    """
    if isinstance(e, Image.UnidentifiedImageError):
        return ImageErrorReason.DECODE_FAILED
    if isinstance(e, (Image.DecompressionBombError, MemoryError)):
        return ImageErrorReason.TOO_LARGE
    if isinstance(e, (OSError, zipfile.BadZipFile)):
        return ImageErrorReason.READ_ERROR
    return classify_error(e)


def get_image_info(resource: Resource) -> ImageInfo:
    with resource.stream() as stream:
        with Image.open(stream) as image:
            return ImageInfo.from_image(image, resource.info.file_size)


def get_image_info_with_extrema(resource: Resource) -> ImageInfo:
    image_info = get_image_info(resource)
    if image_info.mode is ImageMode.RGBA:
        with Image.open(io.BytesIO(resource.content)) as image:
            image_info.extrema = image.getextrema()
    return image_info


def perform_image_optimization(resource: Resource) -> OptimizationResult:
    buffer = io.BytesIO()
    try:
        streamable = io.BytesIO(resource.content)
        with Image.open(streamable) as image:
            result = optimization_machine(image=image, buffer=buffer, filesize=resource.info.file_size)
    except Exception as e:
        reason = _classify_recipe_error(e)
        logger.warning(f"{resource} optimization aborted ({reason}): {e}")
        return OptimizationResult(
            error=reason,
            original_image=ImageInfo.failed(path=resource.filename, filesize=resource.info.file_size),
        )

    if result.success:
        resource.content = buffer.getvalue()
        if result.new_image.format is ImageFormat.JPEG and result.original_image.format is ImageFormat.PNG:
            result.original_image.path = resource.filename
            result.new_image.path = str(PurePosixPath(resource.filename).with_suffix(".jpg"))
            resource.filename = result.new_image.path

    return result
