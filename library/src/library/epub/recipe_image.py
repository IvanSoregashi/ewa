import io
import logging
from pathlib import PurePosixPath

from library.asserts import require
from library.epub.resources import Resource
from PIL import Image

from library.image.constants import ImageMode, ImageFormat
from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult, ImageSkipReason
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
        percent_comp = int((resource.info.compress_size / resource.info.file_size) * 100)
    except ZeroDivisionError as e:
        percent_comp = 100
    try:
        streamable = io.BytesIO(resource.content)
        with Image.open(streamable) as image:
            result = optimization_machine(image=image, buffer=buffer, filesize=resource.info.file_size, compression=percent_comp,)
    except Exception as e:
        reason = ImageErrorReason.from_error(e)
        logger.warning(f"{resource} optimization aborted ({reason}): {e}")
        return ImageOptimizationResult(
            error=reason,
            original_image=ImageInfo.failed(path=resource.filename, filesize=resource.info.file_size),
        )

    filesize = resource.info.file_size / (1024 * 1024)
    if result.skip:
        if percent_comp < 90:
            logger.warning(f"SKIP {resource.filename} compression {percent_comp}% {filesize:.2f} MB")

    if result.success:
        new_image_info = require(result.new_image)
        percent_conv = int((new_image_info.filesize / result.original_image.filesize) * 100)
        logger.info(f"SUCC {resource.filename} compression {percent_comp}%, {percent_conv}%")
        if new_image_info.filesize >= result.original_image.filesize:
            result.success = False
            result.skip = ImageSkipReason.WORSE_CONVERSION
            return result
        resource.content = buffer.getvalue()
        if new_image_info.format is ImageFormat.JPEG and result.original_image.format is ImageFormat.PNG:
            result.original_image.path = resource.filename
            result.new_image.path = str(PurePosixPath(resource.filename).with_suffix(".jpg"))
            resource.filename = new_image_info.path
        # elif new_image_info.format is ImageFormat.MP4 and result.original_image.format is ImageFormat.GIF:
        #     result.original_image.path = resource.filename
        #     result.new_image.path = str(PurePosixPath(resource.filename).with_suffix(".mp4"))
        #     resource.filename = new_image_info.path

    return result
