"""Tests for oversized animation handling: optimize_gif_image hook (giant gif
-> mp4 via ffmpeg), poster generation, and the .gif -> .mp4 resource rename."""

import io
import shutil
from io import BytesIO
from zipfile import ZipInfo

import pytest
from PIL import Image

from library.epub.recipe_image import perform_image_optimization
from library.epub.resources import Resource
from library.image.constants import ANIMATION_SIZE_LIMIT, ImageFormat
from library.image.models import ImageSkipReason
from library.image.optimize_gif import generate_poster

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="system ffmpeg required")


def make_resource(data: bytes, filename: str = "OEBPS/images/anim.gif") -> Resource:
    info = ZipInfo(filename)
    info.file_size = len(data)
    return Resource(info=info, stream_bytes=lambda i: BytesIO(data))


def make_animated_gif(frames: int = 3, size: int = 64) -> bytes:
    images = [Image.new("RGB", (size, size), (i * 60 % 256, 100, 150)) for i in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="GIF", save_all=True, append_images=images[1:], duration=100, loop=0)
    return buffer.getvalue()


def make_giant_animated_gif(target_size: int = ANIMATION_SIZE_LIMIT + 1, size: int = 300) -> bytes:
    """Random-noise frames compress badly in GIF: probe the per-frame size,
    then generate enough frames to exceed `target_size`."""
    probe = Image.effect_noise((size, size), 64)
    single = io.BytesIO()
    probe.save(single, format="GIF")
    frames_needed = min(500, target_size // max(single.tell(), 1) + 2)
    frames = [Image.effect_noise((size, size), 64).convert("RGB") for _ in range(frames_needed)]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=40, loop=0)
    assert len(buffer.getvalue()) > target_size, f"synthetic gif too small: {len(buffer.getvalue())}"
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# optimize_gif_image hook (via perform_image_optimization, the pipeline entry)
# ---------------------------------------------------------------------------


def test_small_animated_gif_stays_gif():
    # noise frames: above the 50 KB optimization threshold, below the 5 MB
    # animation limit -> must be skipped as HAS_ANIMATION, not converted
    frames = [Image.effect_noise((300, 300), 64).convert("RGB") for _ in range(2)]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    data = buffer.getvalue()
    assert 50 * 1024 < len(data) < ANIMATION_SIZE_LIMIT
    resource = make_resource(data)

    result = perform_image_optimization(resource)

    assert result.skip is ImageSkipReason.HAS_ANIMATION
    assert resource.filename == "OEBPS/images/anim.gif"
    assert resource.content == data


@requires_ffmpeg
def test_giant_animated_gif_converted_to_mp4_and_renamed():
    data = make_giant_animated_gif()
    assert len(data) > ANIMATION_SIZE_LIMIT
    resource = make_resource(data)

    result = perform_image_optimization(resource)

    assert result.success
    assert result.new_image.format is ImageFormat.MP4
    assert resource.filename == "OEBPS/images/anim.mp4"
    assert len(resource.content) < len(data)
    assert resource.content[4:8] == b"ftyp"  # mp4 header


# ---------------------------------------------------------------------------
# poster generation
# ---------------------------------------------------------------------------


def test_generate_poster_first_frame_as_jpeg():
    data = make_animated_gif(frames=3, size=64)
    poster, (width, height) = generate_poster(data)

    assert poster[:2] == b"\xff\xd8"  # jpeg magic
    assert (width, height) == (64, 64)
    with Image.open(io.BytesIO(poster)) as image:
        assert image.format == "JPEG"
        assert getattr(image, "is_animated", False) is False
