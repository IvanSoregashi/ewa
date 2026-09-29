"""Apply image optimization and minimum-saving policy to EPUB resources.

Updates bytes and optional inventory paths; the caller coordinates document links.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from epub.image_analytics import ImageOptimizationRecord
from epub.processing import ProcessingContext
from epub.protocols import EpubOperation
from library.asserts import require
from library.epub.media_type import EpubRole, MediaType
from library.epub.resources import Resource, ResourceIndex
from library.image.constants import ImageFormat
from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult
from library.image.recipe import optimize_image

logger = logging.getLogger(__name__)


@dataclass(kw_only=True)
class OptimizeImages(EpubOperation):
    """Disable PNG-to-JPEG conversion to preserve paths and avoid link updates.

    min_filesize is in bytes. max_dimensions=None keeps the existing size policy;
    (width, height) bounds resizing, with 0 meaning no limit on that axis.
    """

    convert_png_to_jpeg: bool = True
    min_filesize: int = 50 * 1024
    max_dimensions: tuple[int, int] | None = None

    def perform(self, context: ProcessingContext) -> None:
        logger.info("OptimizeImages perform")
        resources = context.epub.resources
        for resource in resources.by_role(EpubRole.IMAGE):
            if resource.media_type is MediaType.IMAGE_SVG:
                continue
            old_path = resource.filename
            start_time = time.time()
            result = perform_image_optimization(
                resource,
                resources=resources,
                convert_png_to_jpeg=self.convert_png_to_jpeg,
                min_filesize=self.min_filesize,
                max_dimensions=self.max_dimensions,
            )
            elapsed_time = time.time() - start_time
            logger.info(f"perform_image_optimization performed {old_path} in {elapsed_time:.2f} seconds")
            context.analytics.append(ImageOptimizationRecord.from_result(context.run_id, result))
            if result.success and resource.filename != old_path:
                context.replacements[old_path] = resource.filename


def perform_image_optimization(
    resource: Resource,
    *,
    resources: ResourceIndex | None = None,
    convert_png_to_jpeg: bool = True,
    min_filesize: int = 50 * 1024,
    max_dimensions: tuple[int, int] | None = None,
) -> ImageOptimizationResult:
    """Optimize bytes; supply the owning index to keep renames indexed."""
    try:
        content = resource.content
    except Exception as e:
        reason = ImageErrorReason.from_error(e)
        logger.warning(f"{resource} optimization aborted ({reason}): {e}")
        return ImageOptimizationResult(
            error=reason,
            original_image=ImageInfo.failed(path=resource.filename, filesize=resource.info.file_size),
        )

    percent_comp = int(resource.info.compress_size / len(content) * 100) if content else 100
    result, optimized = optimize_image(
        content,
        compression=percent_comp,
        convert_png_to_jpeg=convert_png_to_jpeg,
        min_filesize=min_filesize,
        max_dimensions=max_dimensions,
    )
    result.original_image.path = resource.filename
    if result.success:
        new_image_info = require(result.new_image)
        if new_image_info.format is ImageFormat.JPEG and result.original_image.format is ImageFormat.PNG:
            new_path = str(PurePosixPath(resource.filename).with_suffix(".jpg"))
            new_image_info.path = new_path
            if resources is not None:
                resources.rename(resource, new_path)
            else:
                resource.filename = new_path
        resource.content = require(optimized)

    return result
