import io
import logging
from pathlib import PurePosixPath

from library.asserts import require
from library.epub.resources import Resource
from PIL import Image

from library.image.constants import ImageMode, ImageFormat
from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult
from library.image.optimization import optimization_machine

logger = logging.getLogger(__name__)


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


def perform_image_optimization(resource: Resource) -> ImageOptimizationResult:
    buffer = io.BytesIO()
    try:
        streamable = io.BytesIO(resource.content)
        with Image.open(streamable) as image:
            result = optimization_machine(image=image, buffer=buffer, filesize=resource.info.file_size)
    except Exception as e:
        reason = ImageErrorReason.from_error(e)
        logger.warning(f"{resource} optimization aborted ({reason}): {e}")
        return ImageOptimizationResult(
            error=reason,
            original_image=ImageInfo.failed(path=resource.filename, filesize=resource.info.file_size),
        )

    if result.success:
        resource.content = buffer.getvalue()
        new_image_info = require(result.new_image)
        if new_image_info.format is ImageFormat.JPEG and result.original_image.format is ImageFormat.PNG:
            result.original_image.path = resource.filename
            result.new_image.path = str(PurePosixPath(resource.filename).with_suffix(".jpg"))
            resource.filename = new_image_info.path

    return result
