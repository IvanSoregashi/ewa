"""Shared test utilities for image-related tests: generation and read accounting.

Importable from any package's tests (library and plugins alike):
    from library.test_utils.utils_image import generate_image, make_resource
"""

import io
import random
from collections.abc import Callable
from functools import lru_cache
from io import BytesIO
from zipfile import ZipInfo

from PIL import Image

from library.epub.resources import Resource
from library.image.constants import ImageFormat, ImageMode


class CountingBytesIO(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.served = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.served += len(chunk)
        return chunk


class CountingReader:
    """Wraps a real binary file handle, counting served bytes."""

    def __init__(self, handle):
        self._handle = handle
        self.served = 0

    def read(self, size=-1):
        chunk = self._handle.read(size)
        self.served += len(chunk)
        return chunk

    def seek(self, *args):
        return self._handle.seek(*args)

    def tell(self):
        return self._handle.tell()

    def close(self):
        self._handle.close()

    def readable(self):
        return True

    def seekable(self):
        return True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def make_resource(data: bytes, filename: str) -> Resource:
    """Plain resource over in-memory bytes."""
    info = ZipInfo(filename)
    info.file_size = len(data)
    return Resource(info=info, stream_bytes=lambda i: BytesIO(data))


def counted_resource(data: bytes, filename: str) -> tuple[Resource, Callable[[], int]]:
    """Resource whose stream accounting is aggregated across every stream() call."""
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


@lru_cache
def generate_image(
    image_format: ImageFormat,
    mode: ImageMode,
    size: tuple[int, int],
    noise: bool = False,
    alpha: int | None = None,
) -> tuple[bytes, str]:
    """Generate image bytes of the given format/mode/size.

    noise=False -> solid single-color image (compresses well).
    noise=True  -> every pixel random (JPEG will be large and incompressible).
    alpha       -> RGBA only: force the alpha channel to this constant value
                   (e.g. alpha=255 -> useless transparency). None keeps natural alpha.

    Supported combos: PNG+RGB, PNG+RGBA, JPEG+RGB.
    """
    supported = {
        (ImageFormat.PNG, ImageMode.RGB),
        (ImageFormat.PNG, ImageMode.RGBA),
        (ImageFormat.JPEG, ImageMode.RGB),
    }
    if (image_format, mode) not in supported:
        raise ValueError(f"Unsupported format/mode combination: {image_format}/{mode}")
    if alpha is not None and mode is not ImageMode.RGBA:
        raise ValueError(f"alpha is only supported for RGBA, got {mode}")

    if noise:
        channels = 3 if mode is ImageMode.RGB else 4
        raw = random.randbytes(size[0] * size[1] * channels)
        image = Image.frombytes(str(mode), size, raw)
    else:
        image = Image.new(str(mode), size, "red")

    if alpha is not None:
        image.putalpha(Image.new("L", image.size, alpha))

    buffer = BytesIO()
    image.save(buffer, format=str(image_format))
    return (
        buffer.getvalue(),
        f"{size[0]}x{size[1]}x{mode}_{'NOISY' if noise else 'RED'}{'' if alpha is None else f'_A{alpha}'}.{image_format}",
    )
