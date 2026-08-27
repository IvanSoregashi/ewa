"""Header-laziness checks for get_image_header - option A: no production code involved.

The accounting lives entirely in this file: Resource already accepts an injected
stream_bytes callable, which is all we need to count what the reader pulls through.
"""

import io
from io import BytesIO
from pathlib import Path
from zipfile import ZipInfo

import pytest
from PIL import Image

from library.epub.image_recipe import get_image_header
from library.epub.resources import Resource

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


def counted_resource(data: bytes, filename: str) -> tuple[Resource, CountingBytesIO]:
    info = ZipInfo(filename)
    info.file_size = len(data)
    stream = CountingBytesIO(data)
    resource = Resource(info=info, stream_bytes=lambda i: stream)
    return resource, stream

def real_counted_resource(image_name: str) -> tuple[Resource, CountingBytesIO]:
    image_path = images_dir / image_name
    zip_info = ZipInfo.from_file(image_path)
    assert zip_info.file_size == image_path.stat().st_size
    stream = CountingBytesIO(image_path.read_bytes())
    resource = Resource(info=zip_info, stream_bytes=lambda i: stream)
    return resource, stream


def image_with_junk(fmt: str, junk_size: int = len(JUNK)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, format=fmt)
    return buffer.getvalue() + b"\x00" * junk_size


@pytest.fixture(params=["PNG", "JPEG"])
def payload(request) -> tuple[bytes, str]:
    fmt = request.param
    return image_with_junk(fmt), f"image.{fmt.lower()}"

def test_the_file():
    resource, stream = real_counted_resource("cursor-2025-models.png")
    info = get_image_header(resource)
    print()
    print(resource.info)
    print(info)
    print(stream.served)
    info = get_image_header(resource)
    print(stream.served)
    info = get_image_header(resource)
    print(stream.served)


def test_get_image_header_reads_only_header(payload):
    data, filename = payload
    resource, stream = counted_resource(data, filename)

    info = get_image_header(resource)

    assert info.size == (10, 10)
    assert stream.served < 4096, f"read {stream.served} bytes of {len(data)}-byte member"


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
    info = get_image_header(resource)

    assert info.size == (4000, 4000)
    assert stream.served < (len(data) * 0.1), f"read {stream.served} bytes of {len(data)}-byte member"
