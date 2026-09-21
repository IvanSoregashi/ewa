import random
from io import BytesIO

import pytest
from PIL import Image

from library.image.constants import ImageFormat
from library.image.models import ImageErrorReason, ImageSkipReason
from library.image.optimization import optimize_image


def image_bytes(format="PNG", size=(256, 256)):
    buffer = BytesIO()
    with Image.frombytes("RGB", size, random.Random(0).randbytes(size[0] * size[1] * 3)) as image:
        image.save(buffer, format=format)
    return buffer.getvalue()


@pytest.mark.parametrize("convert", [False, True])
def test_png_conversion_is_optional_without_resizing(convert):
    content = image_bytes()
    result, optimized = optimize_image(content, convert_png_to_jpeg=convert, max_dimensions=(0, 0))
    assert result.success == convert
    if convert:
        assert result.new_image is not None and optimized is not None
        assert result.new_image.format == ImageFormat.JPEG
        with Image.open(BytesIO(optimized)) as image:
            assert image.format == "JPEG" and image.size == (256, 256)
    else:
        assert result.skip == ImageSkipReason.NOT_OPTIMIZED
        assert optimized is None


@pytest.mark.parametrize("format", ["PNG", "JPEG", "GIF"])
def test_custom_dimensions_preserve_format_and_aspect_ratio(format):
    content = image_bytes(format, (256, 128))
    result, optimized = optimize_image(
        content,
        convert_png_to_jpeg=False,
        min_filesize=0,
        max_dimensions=(100, 30),
    )
    assert result.success, result
    assert result.new_image is not None and optimized is not None
    assert result.new_image.size == (60, 30)
    assert result.new_image.filesize == len(optimized)
    with Image.open(BytesIO(optimized)) as image:
        assert image.format == format and image.size == (60, 30)


def test_file_size_threshold_is_inclusive_and_configurable():
    content = image_bytes(size=(64, 64))
    skipped, no_bytes = optimize_image(content)
    assert skipped.skip == ImageSkipReason.SMALL_IMAGE and no_bytes is None
    accepted, optimized = optimize_image(content, min_filesize=len(content))
    assert accepted.success and optimized is not None
    skipped, no_bytes = optimize_image(content, min_filesize=len(content) + 1)
    assert skipped.skip == ImageSkipReason.SMALL_IMAGE and no_bytes is None


def test_unreadable_image_has_no_replacement_bytes():
    result, optimized = optimize_image(b"not an image")
    assert result.error == ImageErrorReason.DECODE_FAILED
    assert result.original_image.filesize == 12 and result.original_image.size is None
    assert optimized is None
