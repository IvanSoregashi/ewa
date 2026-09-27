from dataclasses import replace
from io import BytesIO
import random

import pytest
from PIL import Image, PngImagePlugin

from library.image.constants import ImageFormat, ImageMode
from library.image.context import ImageProcessingContext
from library.image import recipe
from library.image.models import ImageErrorReason, ImageSkipReason
from library.image.optimization import optimize_image
from library.image.recipe import (
    convert_image,
    optimize_image_with_context,
    remove_useless_alpha,
    resize_image,
    select_dimensions,
    select_encoding,
    convert_inefficient_png_to_jpeg,
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
    expected, expected_bytes = optimize_image(content, **options)
    result, accepted = optimize_image_with_context(content, **options)
    assert (result.success, result.skip, result.error) == (expected.success, expected.skip, expected.error)
    assert result.original_image == expected.original_image
    assert accepted == expected_bytes
    if result.success:
        assert (result.new_image.size, result.new_image.mode, result.new_image.format, result.new_image.filesize) == (
            expected.new_image.size,
            expected.new_image.mode,
            expected.new_image.format,
            expected.new_image.filesize,
        )
    return result, accepted


def check_output(content, **options):
    result, accepted = optimize_image_with_context(content, **options)
    assert result.error is None
    assert result.success == (accepted is not None)
    if result.success:
        assert len(accepted) * 100 < len(content) * 95
        assert result.new_image.filesize == len(accepted)
        with Image.open(BytesIO(accepted)) as image:
            image.load()
            assert (image.size, image.mode, image.format) == (
                result.new_image.size,
                result.new_image.mode,
                result.new_image.format,
            )
    else:
        assert result.skip in (ImageSkipReason.NOT_OPTIMIZED, ImageSkipReason.WORSE_CONVERSION)
        assert result.new_image is None
    return result, accepted


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
def test_format_and_configuration_round_trips(format, mode, bounds, convert):
    result, _ = check_output(
        image_bytes(format, mode), min_filesize=0, max_dimensions=bounds, convert_png_to_jpeg=convert
    )
    if result.success and not convert:
        assert result.new_image.format == format
    if bounds == (80, 30) and result.success:
        assert result.new_image.size == (48, 30)


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
def test_decisions_preserve_input(format, mode, convert, output_format, quality, monkeypatch):
    content = image_bytes(format, mode)
    with ImageProcessingContext(min_filesize=0, max_dimensions=(80, 30)) as context:
        context.open_bytes_as_image(content)
        original_image = context.image
        pixels = original_image.tobytes()
        original_info = replace(context.original_image_info)

        def unexpected(*args, **kwargs):
            pytest.fail("Decisions must not resize, convert, or save pixels")

        with monkeypatch.context() as decisions:
            for method in ("resize", "convert", "save"):
                decisions.setattr(Image.Image, method, unexpected)
            select_dimensions(context)
            remove_useless_alpha(context)
            if convert:
                convert_inefficient_png_to_jpeg(context)
            select_encoding(context)
        assert context.image is original_image and original_image.tobytes() == pixels
        assert context.original_image_info == context.current_image_info == original_info
        assert context.target_image_info.size == (48, 30)
        assert context.target_image_info.mode == ("RGB" if mode == "RGBA" else mode)
        assert context.target_image_info.format == output_format and context.target_quality == quality
        assert context.candidate is None and context.operations == []


def test_explicit_target_format_does_not_reapply_recipe_eligibility():
    content = image_bytes(noisy=False)
    result, _ = optimize_image_with_context(content, min_filesize=0)
    assert result.skip == ImageSkipReason.NOT_OPTIMIZED

    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        original = context.image
        convert_inefficient_png_to_jpeg(context)
        assert context.target_image_info.format == ImageFormat.PNG
        context.target_image_info.format = ImageFormat.JPEG
        select_encoding(context)
        convert_image(context)
        assert context.image is original  # A format change needs no pixel copy.
    result, encoded = context.outcome()
    assert result.operations[0]["reformat"] == ImageFormat.JPEG
    assert result.operations[0]["new_size"] > len(content)
    assert result.skip == ImageSkipReason.WORSE_CONVERSION and encoded is None


def test_png_conversion_uses_current_density_before_resizing():
    content = image_bytes(noisy=False)
    with ImageProcessingContext(max_dimensions=(4, 4)) as context:
        context.open_bytes_as_image(content)
        convert_inefficient_png_to_jpeg(context)
        assert context.target_image_info.format == ImageFormat.PNG
        select_dimensions(context)
        convert_inefficient_png_to_jpeg(context)
        assert context.target_image_info.format == ImageFormat.PNG
        assert context.current_image_info.size == context.original_image_info.size == (160, 100)


def test_execution_uses_custom_target_without_policy_decisions():
    content = image_bytes()
    with ImageProcessingContext(target_quality=42) as context:
        context.open_bytes_as_image(content)
        context.target_image_info.mode = ImageMode.L
        context.target_image_info.format = ImageFormat.JPEG
        convert_image(context)
        context.target_image_info.size = (40, 25)
        resize_image(context)
    result, encoded = context.outcome()
    assert result.success
    assert result.new_image.size == (40, 25) and result.new_image.mode == ImageMode.L
    with (
        Image.open(BytesIO(content)) as source,
        source.convert("L") as converted,
        converted.resize((40, 25), Image.Resampling.LANCZOS) as resized,
        BytesIO() as buffer,
    ):
        resized.save(buffer, format="JPEG", quality=42, optimize=True)
        assert encoded == buffer.getvalue()
    assert [op["accepted"] for op in result.operations] == [True, True]


def test_matching_target_skips_transformations(monkeypatch):
    content = image_bytes()

    def unexpected(*args, **kwargs):
        pytest.fail("An unchanged PNG should not transform or save pixels")

    for method in ("resize", "convert", "save"):
        monkeypatch.setattr(Image.Image, method, unexpected)
    result, encoded = optimize_image_with_context(content, min_filesize=0, convert_png_to_jpeg=False)
    assert result.skip == ImageSkipReason.NOT_OPTIMIZED and encoded is None
    assert result.operations == []


@pytest.mark.parametrize("accept_conversion", [False, True])
@pytest.mark.parametrize("accept_resize", [False, True])
def test_stages_keep_only_accepted_image_and_record_attempts(monkeypatch, accept_conversion, accept_resize):
    content = image_bytes(mode="RGBA")
    conversion_size = len(content) // 2 if accept_conversion else len(content) + 1
    before_resize = conversion_size if accept_conversion else len(content)
    resize_size = before_resize // 2 if accept_resize else before_resize + 1
    context = ImageProcessingContext(min_filesize=0, max_dimensions=(80, 30))
    monkeypatch.setattr(recipe, "ImageProcessingContext", lambda **options: context)
    calls = []
    open_image = Image.open
    opens = []

    def track_open(*args, **kwargs):
        image = open_image(*args, **kwargs)
        opens.append(image)
        return image

    def save(image, buffer, **options):
        calls.append((image.mode, image.size, options))
        buffer.write(bytes(conversion_size if len(calls) == 1 else resize_size))

    monkeypatch.setattr(Image, "open", track_open)
    monkeypatch.setattr(Image.Image, "save", save)
    result, encoded = optimize_image_with_context(content, min_filesize=0, max_dimensions=(80, 30))
    assert len(opens) == 1
    assert calls[0][0:2] == ("RGB", (160, 100))
    expected_mode = ImageMode.RGB if accept_conversion else ImageMode.RGBA
    expected_format = ImageFormat.JPEG if accept_conversion else ImageFormat.PNG
    assert calls[1][0:2] == (expected_mode, (48, 30))
    assert calls[1][2]["format"] == expected_format
    assert calls[1][2].get("quality") == (85 if accept_conversion else None)
    assert [op["new_size"] for op in result.operations] == [conversion_size, resize_size]
    assert [op["old_size"] for op in result.operations] == [len(content), before_resize]
    assert [op["accepted"] for op in result.operations] == [accept_conversion, accept_resize]
    assert result.operations[0]["convert"] == "RGB"
    assert result.operations[0]["reformat"] == ImageFormat.JPEG
    assert result.operations[1]["resize"] == (48, 30)
    assert all("after" not in op and "before" not in op for op in result.operations)
    assert context.current_image_info == context.target_image_info
    assert context.original_image_info.mode == ImageMode.RGBA
    if accept_conversion or accept_resize:
        assert result.success and len(encoded) == (resize_size if accept_resize else conversion_size)
        assert result.new_image.size == ((48, 30) if accept_resize else (160, 100))
        assert result.new_image.mode == expected_mode and result.new_image.format == expected_format
    else:
        assert result.skip == ImageSkipReason.WORSE_CONVERSION and encoded is None
        assert context.current_image_info == context.original_image_info
        assert result.new_image is None


@pytest.mark.parametrize("accept_conversion,expected_width", [(True, 2560), (False, 1080)])
def test_resize_uses_accepted_format_and_measured_bpp(monkeypatch, accept_conversion, expected_width):
    content = image_bytes(size=(2800, 40))
    calls = []
    conversion_size = 5600 if accept_conversion else len(content) + 1

    def save(image, buffer, **options):
        calls.append((image.size, options["format"]))
        buffer.write(bytes(conversion_size if len(calls) == 1 else 1000))

    monkeypatch.setattr(Image.Image, "save", save)
    result, encoded = optimize_image_with_context(content, min_filesize=0)
    assert result.success and len(encoded) == 1000
    assert calls[0] == ((2800, 40), ImageFormat.JPEG)
    assert calls[1][0][0] == expected_width
    assert calls[1][1] == (ImageFormat.JPEG if accept_conversion else ImageFormat.PNG)


def test_accepted_conversion_is_not_saved_again_when_no_resize_needed(monkeypatch):
    content = image_bytes(mode="RGBA")
    calls = []

    def save(image, buffer, **options):
        calls.append(image.size)
        buffer.write(b"converted image")

    monkeypatch.setattr(Image.Image, "save", save)
    result, encoded = optimize_image_with_context(content, min_filesize=0, max_dimensions=(0, 0))
    assert result.success and encoded == b"converted image"
    assert calls == [(160, 100)]


@pytest.mark.parametrize(
    "format,bpp,width",
    [("PNG", 0.199, 2560), ("PNG", 0.2, 1080), ("JPEG", 0.099, 2560), ("JPEG", 0.1, 1080), ("GIF", 0.01, 1080)],
)
def test_dimension_thresholds_use_current_info(format, bpp, width):
    context = ImageProcessingContext()
    context.current_image_info = replace(
        context.current_image_info, format=ImageFormat(format), size=(3000, 100), filesize=round(bpp * 3000 * 100)
    )
    select_dimensions(context)
    assert context.target_image_info.width == width
    context.max_dimensions = (1500, 0)
    select_dimensions(context)
    assert context.target_image_info.width == 1500


@pytest.mark.parametrize("format", ["PNG", "JPEG", "GIF"])
@pytest.mark.parametrize("noisy", [False, True])
def test_density_based_defaults(format, noisy):
    check_output(image_bytes(format, size=(2800, 40), noisy=noisy), min_filesize=0)


@pytest.mark.parametrize("alpha", [0, 249, 250, 255])
@pytest.mark.parametrize("convert", [False, True])
def test_transparency_policy(alpha, convert):
    compare(image_bytes(mode="RGBA", alpha=alpha), min_filesize=0, convert_png_to_jpeg=convert)


@pytest.mark.parametrize("convert", [False, True])
def test_alpha_decision_uses_original_pixels_before_resizing(convert, monkeypatch):
    with Image.new("RGBA", (16, 16), (120, 80, 40, 255)) as image, BytesIO() as buffer:
        image.putpixel((8, 8), (120, 80, 40, 249))
        image.save(buffer, format="PNG")
        content = buffer.getvalue()
        with image.resize((2, 2), Image.Resampling.LANCZOS) as resized:
            assert resized.getextrema()[3][0] >= 250
    context = ImageProcessingContext(min_filesize=0, max_dimensions=(2, 2))
    monkeypatch.setattr(recipe, "ImageProcessingContext", lambda **options: context)
    result, _ = optimize_image_with_context(content, convert_png_to_jpeg=convert)
    assert result.error is None
    assert context.current_image_info.mode == ImageMode.RGBA
    assert context.current_image_info.format == ImageFormat.PNG
    assert len(result.operations) == 1 and result.operations[0]["resize"] == (2, 2)
    assert "convert" not in result.operations[0] and "reformat" not in result.operations[0]


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


@pytest.mark.parametrize(
    "method,error",
    [
        ("resize", MemoryError("pixels")),
        ("save", ValueError("encoder failed")),
        ("convert", ValueError("cannot write mode")),
        ("getextrema", OSError("broken pixels")),
    ],
)
def test_processing_failures_match(method, error, monkeypatch):
    content = image_bytes(mode="RGBA")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(Image.Image, method, fail)
    previous, _ = optimize_image(content, min_filesize=0, max_dimensions=(80, 30))
    result, accepted = optimize_image_with_context(content, min_filesize=0, max_dimensions=(80, 30))
    assert result.error == previous.error and result.original_image == previous.original_image
    assert accepted is None
    if method == "resize":
        assert result.new_image.format == ImageFormat.JPEG
        assert result.new_image.size == (160, 100)
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
