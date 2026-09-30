"""Apply image optimization and minimum-saving policy to EPUB resources.

Updates bytes and optional inventory paths; the caller coordinates document links.
"""

import logging
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
        resources = context.epub.resources
        for resource in resources.by_role(EpubRole.IMAGE):
            if resource.media_type is MediaType.IMAGE_SVG:
                continue
            old_path = resource.filename
            result = perform_image_optimization(
                resource,
                resources=resources,
                convert_png_to_jpeg=self.convert_png_to_jpeg,
                min_filesize=self.min_filesize,
                max_dimensions=self.max_dimensions,
            )
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
            jpeg_path = PurePosixPath(resource.filename).with_suffix(".jpg")
            new_path = str(jpeg_path)
            if resources is not None:
                number = 1
                while resources.by_path(new_path) is not None:
                    new_path = str(jpeg_path.with_name(f"{jpeg_path.stem}_{number}.jpg"))
                    number += 1
                resources.rename(resource, new_path)
            else:
                resource.filename = new_path
            new_image_info.path = new_path
        resource.content = require(optimized)

    return result
