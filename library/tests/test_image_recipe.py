from dataclasses import replace
from io import BytesIO
import random

import pytest
from PIL import Image, PngImagePlugin

from library.image.context import ImageProcessingContext
from library.image.models import ImageErrorReason, ImageSkipReason
from library.image.optimization import optimize_image
from library.image.recipe import (
    needs_encoding,
    optimize_image_with_context,
    png_to_jpeg,
    remove_useless_alpha,
    resize_image,
    save_image,
    select_encoding,
    convert_inefficient_png_to_jpeg,
    worthwhile_savings,
)


def image_bytes(format="PNG", mode="RGB", size=(160, 100), *, noisy=True, alpha=255, animated=False):
    pixels = random.Random(42).randbytes(size[0] * size[1] * 3) if noisy else bytes(size[0] * size[1] * 3)
    with BytesIO() as buffer, Image.frombytes("RGB", size, pixels) as rgb:
        image = rgb.convert(mode)
        try:
            if mode == "RGBA":
                image.putalpha(alpha)
            if animated:
                with Image.new(mode, size, "white") as second:
                    image.save(buffer, format=format, save_all=True, append_images=[second], duration=100, loop=0)
            else:
                image.save(buffer, format=format)
            return buffer.getvalue()
        finally:
            image.close()


def compare(content, **options):
    expected = optimize_image(content, **options)
    actual = optimize_image_with_context(content, **options)
    assert actual == expected
    result, accepted = actual
    assert result.success == (accepted is not None)
    return actual


@pytest.mark.parametrize(
    "format,mode",
    [
        ("PNG", "RGB"),
        ("PNG", "RGBA"),
        ("PNG", "L"),
        ("PNG", "LA"),
        ("PNG", "P"),
        ("JPEG", "RGB"),
        ("JPEG", "L"),
        ("JPEG", "CMYK"),
        ("GIF", "P"),
        ("BMP", "RGB"),
    ],
)
@pytest.mark.parametrize("bounds", [None, (0, 0), (80, 0), (0, 40), (80, 30)])
@pytest.mark.parametrize("convert", [False, True])
def test_format_and_configuration_comparisons(format, mode, bounds, convert):
    compare(image_bytes(format, mode), min_filesize=0, max_dimensions=bounds, convert_png_to_jpeg=convert)


@pytest.mark.parametrize(
    "format,mode,convert,output_format,quality",
    [
        ("PNG", "RGB", True, "JPEG", 85),
        ("PNG", "RGBA", True, "JPEG", 85),
        ("PNG", "RGB", False, "PNG", None),
        ("JPEG", "RGB", True, "JPEG", 75),
        ("GIF", "P", True, "GIF", 85),
    ],
)
def test_manipulations_conversion_and_encoding_are_independent(format, mode, convert, output_format, quality):
    content = image_bytes(format, mode)
    options = {"min_filesize": 0, "max_dimensions": (80, 30), "convert_png_to_jpeg": convert}
    with ImageProcessingContext(min_filesize=0, max_dimensions=(80, 30)) as context:
        context.open_bytes_as_image(content)
        resize_image(context)
        resized_size = context._image.size
        assert resized_size == (48, 30)
        assert context._image.mode == mode and context.output_format == format
        remove_useless_alpha(context)
        working_image = context._image
        assert working_image.size == resized_size
        assert working_image.mode == ("RGB" if mode == "RGBA" else mode)
        assert context.output_format == format
        if convert and convert_inefficient_png_to_jpeg(context):
            png_to_jpeg(context)
        assert context._image is working_image and context.output_quality is None
        assert context.original_image_info.format == format
        context.verify(needs_encoding)
        select_encoding(context)
        assert context._image is working_image
        assert context.output_format == output_format and context.output_quality == quality
        assert context.candidate is None and context.new_image_info is None
        save_image(context)
        context.verify(worthwhile_savings)
        context.succeed()
    assert context.outcome() == optimize_image(content, **options)


def test_explicit_conversion_does_not_reapply_recipe_eligibility():
    content = image_bytes(noisy=False)
    result, _ = optimize_image_with_context(content, min_filesize=0)
    assert result.skip == ImageSkipReason.NOT_OPTIMIZED

    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        assert not convert_inefficient_png_to_jpeg(context)
        png_to_jpeg(context)
        select_encoding(context)
        save_image(context)
        encoded = context.candidate
        context.verify(worthwhile_savings)
        context.succeed()
    with Image.open(BytesIO(encoded)) as image:
        assert image.format == "JPEG"
    assert context.outcome()[0].new_image.format == "JPEG"


@pytest.mark.parametrize("format", ["PNG", "JPEG", "GIF"])
@pytest.mark.parametrize("noisy", [False, True])
def test_density_based_defaults(format, noisy):
    compare(image_bytes(format, size=(2800, 40), noisy=noisy), min_filesize=0)


@pytest.mark.parametrize("alpha", [0, 249, 250, 255])
@pytest.mark.parametrize("convert", [False, True])
def test_transparency_policy(alpha, convert):
    compare(image_bytes(mode="RGBA", alpha=alpha), min_filesize=0, convert_png_to_jpeg=convert)


@pytest.mark.parametrize("format", ["PNG", "GIF"])
def test_animations_and_size_gate_order(format):
    content = image_bytes(format, animated=True)
    result, _ = compare(content, min_filesize=0)
    assert result.skip == ImageSkipReason.HAS_ANIMATION
    result, _ = compare(content, min_filesize=len(content) + 1)
    assert result.skip == ImageSkipReason.SMALL_IMAGE


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_minimum_size_boundary(delta):
    content = image_bytes()
    result, _ = compare(content, min_filesize=len(content) + delta)
    assert result.skip == ImageSkipReason.SMALL_IMAGE if delta > 0 else result.success


@pytest.mark.parametrize("compression", [74, 75, 100])
def test_jpeg_zip_compression_policy(compression):
    result, _ = compare(image_bytes("JPEG", noisy=False), min_filesize=0, compression=compression)
    if compression >= 75:
        assert result.skip == ImageSkipReason.NOT_OPTIMIZED
    else:
        assert result.success or result.skip == ImageSkipReason.WORSE_CONVERSION


@pytest.mark.parametrize("size", [(1, 4000), (4000, 1), (400, 200)])
def test_committed_resize_bounds(size):
    compare(image_bytes(size=size), min_filesize=0, max_dimensions=(100, 30))


@pytest.mark.parametrize("content", [b"", b"not an image"])
def test_invalid_bytes(content):
    result, _ = compare(content)
    assert result.error == ImageErrorReason.DECODE_FAILED


def test_truncated_pixel_data_matches():
    content = image_bytes()
    result, _ = compare(content[: len(content) // 2], min_filesize=0, max_dimensions=(80, 30))
    assert result.error is not None and result.original_image.size == (160, 100)


@pytest.mark.parametrize("percentage", [97.0, 97.9, 98.0, 100.0])
def test_encoded_size_boundary_matches_original(percentage, monkeypatch):
    content = image_bytes()
    size = int(len(content) * percentage / 100)

    def save(image, buffer, **options):
        buffer.write(bytes(size))

    monkeypatch.setattr(Image.Image, "save", save)
    result, accepted = compare(content, min_filesize=0)
    assert result.new_image.filesize == size
    assert result.success == (int(size / len(content) * 100) <= 97)
    if not result.success:
        assert result.skip == ImageSkipReason.WORSE_CONVERSION and accepted is None


@pytest.mark.parametrize(
    "method,error",
    [
        ("resize", MemoryError("pixels")),
        ("save", ValueError("encoder failed")),
        ("getextrema", OSError("broken pixels")),
    ],
)
def test_processing_failures_match(method, error, monkeypatch):
    content = image_bytes(mode="RGBA")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(Image.Image, method, fail)
    result, _ = compare(content, min_filesize=0, max_dimensions=(80, 30))
    assert result.error is not None and result.original_image.size == (160, 100)


def test_small_skip_does_not_decode_pixels(monkeypatch):
    content = image_bytes()

    def fail(*args, **kwargs):
        pytest.fail("A small image must skip before pixel decoding")

    monkeypatch.setattr(PngImagePlugin.PngImageFile, "load", fail)
    result, _ = compare(content, min_filesize=len(content) + 1)
    assert result.skip == ImageSkipReason.SMALL_IMAGE


def test_ordered_checks_stop_at_first_failure():
    calls = []

    def passes(context):
        calls.append("pass")

    def skips(context):
        calls.append("skip")
        return ImageSkipReason.NOT_OPTIMIZED

    def unreachable(context):
        pytest.fail("Checks must stop at the first failure")

    with ImageProcessingContext() as context:
        context.verify(passes, skips, unreachable)
        pytest.fail("A failed check must stop the recipe")
    assert calls == ["pass", "skip"]
    assert context.outcome()[0].skip == ImageSkipReason.NOT_OPTIMIZED


@pytest.mark.parametrize("output_size,accepted", [(970, True), (979, True), (980, False), (1000, False)])
def test_savings_gate_keeps_candidate_evidence(output_size, accepted):
    with ImageProcessingContext() as context:
        context.original_image_info.filesize = 1000
        context.new_image_info = replace(context.original_image_info, filesize=output_size)
        context.candidate = bytes(output_size)
        context.verify(worthwhile_savings)
        context.succeed()
    result, content = context.outcome()
    assert result.success == accepted
    assert (content is not None) == accepted
    assert result.new_image.filesize == output_size
    if not accepted:
        assert result.skip == ImageSkipReason.WORSE_CONVERSION
