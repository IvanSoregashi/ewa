"""Header-laziness checks for get_image_header - option A: no production code involved.

The accounting lives entirely in this file: Resource already accepts an injected
stream_bytes callable, which is all we need to count what the reader pulls through.
"""

import io
import random
from collections.abc import Callable
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from zipfile import ZipInfo

import pytest

from PIL import Image

from library.epub.image_recipe import get_image_info, get_image_info_with_extrema
from library.epub.resources import Resource
from library.image.constants import ImageFormat, ImageMode

JUNK = b"\x00" * (5 * 1024 * 1024)
images_dir = Path("samples") / "images"


class CountingBytesIO(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.served = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.served += len(chunk)
        return chunk


def counted_resource(data: bytes, filename: str) -> tuple[Resource, Callable[[], int]]:
    info = ZipInfo(filename)
    info.file_size = len(data)

    streams: list[CountingBytesIO] = []

    def stream_bytes(info: ZipInfo) -> CountingBytesIO:
        stream = CountingBytesIO(data)  # fresh instance per stream() call
        streams.append(stream)
        return stream

    def total_served() -> int:
        return sum(s.served for s in streams)

    return Resource(info=info, stream_bytes=stream_bytes), total_served


def real_counted_resource(image_name: str) -> tuple[Resource, Callable[[], int]]:
    """data is read from disk ONCE at setup - not part of the accounting."""
    image_path = images_dir / image_name
    data = image_path.read_bytes()
    info = ZipInfo.from_file(image_path)

    streams: list[CountingBytesIO] = []

    def stream_bytes(info: ZipInfo) -> CountingBytesIO:
        stream = CountingBytesIO(data)  # fresh instance per stream() call
        streams.append(stream)
        return stream

    def total_served() -> int:
        return sum(s.served for s in streams)

    return Resource(info=info, stream_bytes=stream_bytes), total_served

@lru_cache
def generate_image(image_format: ImageFormat, mode: ImageMode, size: tuple[int, int], noise: bool = False,) -> tuple[bytes, str]:
    """Generate image bytes of the given format/mode/size.

    noise=False -> solid single-color image (compresses well).
    noise=True  -> every pixel random (JPEG will be large and incompressible).

    Supported combos: PNG+RGB, PNG+RGBA, JPEG+RGB.
    """
    supported = {
        (ImageFormat.PNG, ImageMode.RGB),
        (ImageFormat.PNG, ImageMode.RGBA),
        (ImageFormat.JPEG, ImageMode.RGB),
    }
    if (image_format, mode) not in supported:
        raise ValueError(f"Unsupported format/mode combination: {image_format}/{mode}")

    if noise:
        channels = 3 if mode is ImageMode.RGB else 4
        raw = random.randbytes(size[0] * size[1] * channels)
        image = Image.frombytes(str(mode), size, raw)
    else:
        image = Image.new(str(mode), size, "red")

    buffer = BytesIO()
    image.save(buffer, format=str(image_format))
    return buffer.getvalue(), f"{size[0]}x{size[1]}x{mode}_{"NOISY" if noise else "RED"}.{image_format}"


def test_the_file(resource, total_streamed):
    resource, total_streamed = real_counted_resource("cursor-2025-models.png")
    size = resource.info.file_size

    print()
    print(resource.info)
    info = get_image_info(resource)
    print(info)
    print(total_streamed())
    get_image_info(resource)
    print(total_streamed())
    print(f"{get_image_info_with_extrema(resource)=}")
    print(total_streamed())
    resource.content
    print(total_streamed())
    get_image_info(resource)
    print(total_streamed())
    get_image_info_with_extrema(resource)
    print(total_streamed())


def test_get_image_header_reads_only_header():
    image_size = (1000, 1000)
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGB, image_size)
    resource, total_streamed = counted_resource(image_bytes, filename)

    info = get_image_info(resource)

    assert info.size == image_size
    print(total_streamed())
    print(total_streamed())
    info = get_image_info(resource)
    print(total_streamed())
    info = get_image_info_with_extrema(resource)
    print(total_streamed())
    assert total_streamed() < 4096, f"read {total_streamed()} bytes of {len(image_bytes)}-byte member"


def test_full_read_registers_exactly_payload_size():
    """Control: if anything goes eager, the counter catches it."""
    data = image_with_junk("PNG")
    resource, stream = counted_resource(data, "image.png")

    assert len(resource.content) == len(data)
    assert stream.served == len(data)


def test_bigger_dimensions_stay_cheap():
    """A large-declared JPEG still opens from its header alone."""
    buffer = BytesIO()
    Image.new("RGB", (4000, 4000), "blue").save(buffer, format="JPEG", quality=95)
    data = buffer.getvalue()

    resource, stream = counted_resource(data, "image.jpg")
    info = get_image_info(resource)

    assert info.size == (4000, 4000)
    assert stream.served < (len(data) * 0.1), f"read {stream.served} bytes of {len(data)}-byte member"
