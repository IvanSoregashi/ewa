"""Giant animated GIF -> MP4 conversion.

The conversion itself flows through the regular image optimization entry point
(perform_image_optimization -> optimization_machine -> optimize_gif_image),
which transcodes oversized animations and renames the resource (.gif -> .mp4).
On top of that this recipe:
  - generates the same-basename JPEG poster (new resource + manifest item),
  - updates the manifest via the existing replacement mechanism
    (recipe_package.replace_links),
  - returns the table for chapter rewriting (recipe_html.replace_gifs_with_videos).
"""

import io
import logging
from pathlib import PurePosixPath
from zipfile import ZipInfo

from PIL import Image

from library.epub.epub import EPUB
from library.epub.media_type import EpubRole, MediaType
from library.epub.recipe_html import VideoTagInfo, replace_gifs_with_videos
from library.epub.recipe_image import perform_image_optimization
from library.epub.resources import Resource
from library.epub.utils_href import posix_relative_href
from library.image.constants import ANIMATION_SIZE_LIMIT
from library.image.optimize_gif import generate_poster

from epub.recipe_package import replace_links as replace_manifest_links

logger = logging.getLogger(__name__)


def convert_giant_gifs(epub: EPUB, size_limit: int = ANIMATION_SIZE_LIMIT) -> dict[str, VideoTagInfo]:
    """Convert every oversized animated GIF to MP4 + same-basename JPEG poster.

    Static gifs and failed conversions (no ffmpeg, ffmpeg error) keep their gif
    untouched. Returns the table for chapter rewriting:
    {old gif archive path: VideoTagInfo}.
    """
    table: dict[str, VideoTagInfo] = {}
    manifest = epub.core.manifest
    opf_path = epub.core.package_resource.filename

    for resource in list(epub.resources):
        if resource.media_type is not MediaType.IMAGE_GIF or resource.info.file_size <= size_limit:
            continue

        with Image.open(io.BytesIO(resource.content)) as image:
            if not getattr(image, "is_animated", False):
                logger.info(f"{resource} is a static gif, keeping it")
                continue
            width, height = image.size

        video_manifest = manifest.by_path(posix_relative_href(opf_path, resource.filename))
        if video_manifest is None:
            logger.warning(f"{resource} has no manifest item, keeping gif")
            continue

        try:
            poster_bytes, _ = generate_poster(resource.content)
        except Exception as error:
            logger.warning(f"{resource} poster generation failed, keeping gif: {error}")
            continue

        old_path = resource.filename
        result = perform_image_optimization(resource)
        if not result.success:
            logger.warning(f"{resource} conversion failed ({result.skip or result.error}), keeping gif")
            continue

        new_path = resource.filename  # renamed to .mp4 by perform_image_optimization
        epub.resources.rename(resource, old_path)  # re-key the index (filename changed in place)
        replace_manifest_links(epub, {old_path: new_path})
        poster_path = _add_poster_resource(epub, video_manifest, new_path, poster_bytes)

        table[old_path] = VideoTagInfo(
            video_path=new_path,
            poster_path=poster_path,
            width=width,
            height=height,
            alt=PurePosixPath(old_path).name,
        )
        logger.info(f"{old_path} converted to {new_path} + poster")

    if table:
        epub.core.package_resource.content = epub.core.package.to_xml_bytes()
        epub.core._manifest = None
    return table


def _add_poster_resource(epub: EPUB, video_manifest, mp4_path: str, poster_bytes: bytes) -> str:
    """Add the poster as a resource and a manifest item (same basename as the mp4)."""
    poster_path = str(PurePosixPath(mp4_path).with_suffix(".jpg"))
    info = ZipInfo(poster_path)
    info.file_size = len(poster_bytes)
    poster = Resource(info=info, stream_bytes=lambda i: io.BytesIO(poster_bytes))
    poster.content = poster_bytes
    epub.resources.add(poster)

    epub.core.package.manifest.add_item(
        id=f"{video_manifest.item.id}-poster",
        href=posix_relative_href(epub.core.package_resource.filename, poster_path),
        media_type=MediaType.IMAGE_JPEG.value,
    )
    return poster_path


def rewrite_gif_chapters(epub: EPUB, table: dict[str, VideoTagInfo]) -> int:
    """Swap <img> elements of converted animations for video tags in all
    chapters. Returns the number of replaced images."""
    replaced = 0
    for resource in epub.resources.by_role(EpubRole.HTML):
        replaced += replace_gifs_with_videos(resource, table)
    return replaced
