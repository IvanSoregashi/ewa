"""Convert large animations separately from the static-image optimizer."""

import io
import logging
from pathlib import PurePosixPath

from PIL import Image

from library.epub.epub import EPUB
from library.epub.media_type import EpubRole, MediaType
from epub.recipe_html import VideoTagInfo, replace_gifs_with_videos
from library.epub.resources import Resource
from library.image.constants import ANIMATION_CRF, ANIMATION_SIZE_LIMIT
from library.image.optimize_gif import convert_to_mp4, generate_poster

from epub.recipe_package import replace_links as replace_manifest_links

logger = logging.getLogger(__name__)


def convert_giant_gifs(epub: EPUB, size_limit: int = ANIMATION_SIZE_LIMIT) -> dict[str, VideoTagInfo]:
    """Convert every oversized animated GIF to MP4 + same-basename JPEG poster.

    Static gifs and failed conversions (no ffmpeg, ffmpeg error) keep their gif
    untouched. Returns the table for chapter rewriting:
    {old gif archive path: VideoTagInfo}.
    """
    table: dict[str, VideoTagInfo] = {}

    for resource in list(epub.resources):
        if resource.media_type is not MediaType.IMAGE_GIF:
            continue

        video_manifest = epub.package.manifest_item_by_path(resource.filename)
        if video_manifest is None:
            logger.warning(f"{resource} has no manifest item, keeping gif")
            continue

        try:
            content = resource.content
            if len(content) <= size_limit:
                continue
            with io.BytesIO(content) as source, Image.open(source) as image:
                if not getattr(image, "is_animated", False):
                    continue
                width, height = image.size
                video_bytes, details = convert_to_mp4(image, len(content), crf=ANIMATION_CRF, source_bytes=content)
            if video_bytes is None:
                logger.warning("%s conversion skipped: %s", resource, details)
                continue
            poster_bytes, _ = generate_poster(content)
        except Exception as error:
            logger.warning("%s conversion failed, keeping gif: %s", resource, error)
            continue

        if (len(video_bytes) + len(poster_bytes)) * 100 >= len(content) * 95:
            logger.info("%s video and poster save too little, keeping gif", resource)
            continue

        old_path = resource.filename
        new_path = str(PurePosixPath(old_path).with_suffix(".mp4"))
        path_collision = any(
            other.filename == new_path
            or other.filename.startswith(new_path + "/")
            or new_path.startswith(other.filename.rstrip("/") + "/")
            and not other.info.is_dir()
            for other in epub.resources
        )
        if path_collision or epub.package.manifest_item_by_path(new_path) is not None:
            raise ValueError(f"Video path already exists: {new_path!r}")
        # Poster creation validates collisions before changing the GIF.
        poster_path = _add_poster_resource(epub, video_manifest, new_path, poster_bytes)
        epub.resources.rename(resource, new_path)
        resource.content = video_bytes
        replace_manifest_links(epub, {old_path: new_path})

        table[old_path] = VideoTagInfo(
            video_path=new_path,
            poster_path=poster_path,
            width=width,
            height=height,
            alt=PurePosixPath(old_path).name,
        )
        logger.info(f"{old_path} converted to {new_path} + poster")

    if table:
        epub.package.flush()
    return table


def _add_poster_resource(epub: EPUB, video_manifest, mp4_path: str, poster_bytes: bytes) -> str:
    """Add the poster as a resource and a manifest item (same basename as the mp4)."""
    poster_path = str(PurePosixPath(mp4_path).with_suffix(".jpg"))
    poster = Resource.from_bytes(poster_path, poster_bytes)
    epub.package.add_resource(
        poster,
        item_id=f"{video_manifest.id}-poster",
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
