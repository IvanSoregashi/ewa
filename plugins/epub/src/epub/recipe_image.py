"""Apply image optimization and minimum-saving policy to EPUB resources.

Updates bytes and optional inventory paths; the caller coordinates document links.
"""

import io
import logging
from pathlib import PurePosixPath
from PIL import Image
from library.asserts import require
from library.epub.resources import Resource, ResourceIndex
from library.image.constants import ImageFormat
from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult, ImageSkipReason
from library.image.optimization import optimization_machine

logger = logging.getLogger(__name__)


def perform_image_optimization(
    resource: Resource, *, resources: ResourceIndex | None = None
) -> ImageOptimizationResult:
    """Optimize bytes; supply the owning index to keep renames indexed."""
    buffer = io.BytesIO()
    try:
        percent_comp = int((resource.info.compress_size / resource.info.file_size) * 100)
    except ZeroDivisionError:
        percent_comp = 100

    try:
        streamable = io.BytesIO(resource.content)
        with Image.open(streamable) as image:
            result = optimization_machine(
                image=image,
                buffer=buffer,
                filesize=resource.info.file_size,
                compression=percent_comp,
            )

    except Exception as e:
        reason = ImageErrorReason.from_error(e)
        logger.warning(f"{resource} optimization aborted ({reason}): {e}")
        return ImageOptimizationResult(
            error=reason,
            original_image=ImageInfo.failed(path=resource.filename, filesize=resource.info.file_size),
        )

    result.original_image.path = resource.filename
    if result.success:
        new_image_info = require(result.new_image)
        percent_conv = int((new_image_info.filesize / result.original_image.filesize) * 100)
        if percent_conv > 97:
            result.success = False
            result.skip = ImageSkipReason.WORSE_CONVERSION
            return result

        if new_image_info.format is ImageFormat.JPEG and result.original_image.format is ImageFormat.PNG:
            result.new_image.path = str(PurePosixPath(resource.filename).with_suffix(".jpg"))
            if resources is not None:
                resources.rename(resource, new_image_info.path)
            else:
                resource.filename = new_image_info.path
        resource.content = buffer.getvalue()

    return result
