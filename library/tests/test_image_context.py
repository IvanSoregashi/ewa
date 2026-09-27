from dataclasses import replace
from io import BytesIO
import json
import pickle
import random

import pytest
from PIL import Image

from library.image.constants import ImageFormat, ImageMode
from library.image.context import ImageProcessingContext
from library.image.models import ImageErrorReason, ImageInfo, ImageSkipReason


@pytest.fixture
def content():
    pixels = random.Random(42).randbytes(80 * 50 * 3)
    with BytesIO() as buffer, Image.frombytes("RGB", (80, 50), pixels) as image:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def assert_closed(*images):
    for image in images:
        with pytest.raises(ValueError):
            image.getpixel((0, 0))


def test_success_owns_input_and_transformed_images(content):
    with ImageProcessingContext(compression=80, min_filesize=0, max_dimensions=(0, 0)) as context:
        context.open_bytes_as_image(content)
        original = context.image
        source = original.fp
        transformed = original.resize((40, 25))
        context.replace_image(transformed)
        assert_closed(original)
        assert context.image is transformed
    result, accepted = pickle.loads(pickle.dumps(context.outcome()))
    assert result.success and accepted
    assert result.original_image.size == (80, 50)
    assert result.new_image.size == (40, 25)
    assert result.new_image.filesize == len(accepted)
    assert source.closed and context._image is None
    assert_closed(original, transformed)
    assert context.compression == 80 and context.min_filesize == 0 and context.max_dimensions == (0, 0)
    json.dumps(result.as_dict())


def test_invalid_input_retains_size():
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(b"invalid image")
        pytest.fail("Opening failure must stop the block")
    result, accepted = context.outcome()
    assert result.error == ImageErrorReason.DECODE_FAILED
    assert result.original_image == ImageInfo.failed(filesize=13)
    assert result.new_image is None and accepted is None


def test_open_failure_closes_acquired_buffer(content, monkeypatch):
    sources = []

    def fail(source):
        sources.append(source)
        raise OSError("open failed")

    monkeypatch.setattr(Image, "open", fail)
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
    assert sources[0].closed
    result, accepted = context.outcome()
    assert result.error == ImageErrorReason.READ_ERROR
    assert result.original_image.filesize == len(content) and accepted is None
    assert result.new_image is None


@pytest.mark.parametrize("accept", [False, True])
def test_replacement_keeps_only_accepted_image_and_metadata(content, monkeypatch, accept):
    output_size = len(content) // 2 if accept else len(content) + 1

    def save(image, buffer, **options):
        assert original.getpixel((0, 0)) == original_pixel
        buffer.write(bytes(output_size))

    monkeypatch.setattr(Image.Image, "save", save)
    with ImageProcessingContext(target_quality=70) as context:
        context.open_bytes_as_image(content)
        original = context.image
        original_pixel = original.getpixel((0, 0))
        original_info = replace(context.original_image_info)
        assert (
            len({id(context.original_image_info), id(context.current_image_info), id(context.target_image_info)}) == 3
        )
        context.target_image_info.mode = ImageMode.L
        context.target_image_info.format = ImageFormat.JPEG
        converted = original.convert("L")
        context.replace_image(converted)
        assert context.original_image_info == original_info
        assert context.target_image_info == context.current_image_info
        assert context.target_image_info is not context.current_image_info
        assert context.operations == [
            {
                "convert": "L",
                "reformat": ImageFormat.JPEG,
                "quality": 70,
                "old_size": len(content),
                "new_size": output_size,
                "accepted": accept,
            }
        ]
        if accept:
            assert context.image is converted
            assert context.current_image_info.mode == ImageMode.L
            assert context.current_image_info.format == ImageFormat.JPEG
            assert context.current_image_info.bytes_per_pixel == output_size / (80 * 50)
            assert context.target_quality == 70
            assert_closed(original)
        else:
            assert context.image is original and context.candidate is None
            assert context.current_image_info == original_info
            assert context.target_quality is None
            assert_closed(converted)
    assert_closed(original, converted)
    result, encoded = context.outcome()
    assert result.success == accept
    if not accept:
        assert result.skip == ImageSkipReason.WORSE_CONVERSION
        assert result.new_image is None and encoded is None


@pytest.mark.parametrize("accept", [False, True])
def test_reencoding_current_image_does_not_close_it(content, monkeypatch, accept):
    output_size = len(content) // 2 if accept else len(content)
    monkeypatch.setattr(Image.Image, "save", lambda image, buffer, **options: buffer.write(bytes(output_size)))
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        original = context.image
        pixel = original.getpixel((0, 0))
        context.target_image_info.format = ImageFormat.JPEG
        context.replace_image(original)
        assert context.image is original and original.getpixel((0, 0)) == pixel
        assert context.current_image_info.format == (ImageFormat.JPEG if accept else ImageFormat.PNG)
    assert_closed(original)
    assert context.outcome()[0].success == accept


@pytest.mark.parametrize(
    "output_size,accepted", [(949, True), (950, False), (951, False), (1000, False), (1100, False)]
)
def test_strict_five_percent_savings(content, monkeypatch, output_size, accepted):
    monkeypatch.setattr(Image.Image, "save", lambda image, buffer, **options: buffer.write(bytes(output_size)))
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        context.original_image_info.filesize = context.current_image_info.filesize = 1000
        context.replace_image(context.image)
    result, encoded = context.outcome()
    assert result.success == accepted
    assert (encoded is not None) == accepted
    assert result.operations[0]["new_size"] == output_size
    if not accepted:
        assert result.skip == ImageSkipReason.WORSE_CONVERSION and result.new_image is None


@pytest.mark.parametrize("error", [ValueError("encoder failed"), KeyboardInterrupt()])
def test_encoding_failure_closes_current_and_attempted_images(content, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(Image.Image, "save", fail)
    context = ImageProcessingContext()
    try:
        with context:
            context.open_bytes_as_image(content)
            original = context.image
            source = original.fp
            converted = original.convert("L")
            context.replace_image(converted)
    except KeyboardInterrupt:
        assert isinstance(error, KeyboardInterrupt)
    else:
        assert isinstance(error, Exception)
        assert context.outcome()[0].error == ImageErrorReason.ENCODE_FAILED
    assert source.closed and context.candidate is None and context._image is None
    assert_closed(original, converted)


def test_failure_before_open_is_managed():
    with ImageProcessingContext() as context:
        raise OSError("input acquisition failed")
    result, accepted = context.outcome()
    assert result.error == ImageErrorReason.READ_ERROR
    assert result.original_image == ImageInfo.failed() and accepted is None


def test_metadata_failure_closes_input(content, monkeypatch):
    opened = []

    def fail(image, filesize):
        opened.append((image, image.fp))
        raise ValueError("metadata failure")

    monkeypatch.setattr(ImageInfo, "from_image", fail)
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
    result, accepted = context.outcome()
    assert result.error == ImageErrorReason.UNKNOWN and result.new_image is None
    assert result.original_image.filesize == len(content)
    assert opened[0][1].closed and accepted is None
    assert_closed(opened[0][0])


@pytest.mark.parametrize("processing_error", [None, ValueError("encoder failed")])
def test_cleanup_failure_closes_remaining_resources(content, monkeypatch, processing_error):
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        source = context.image.fp
        transformed = context.image.resize((40, 25))
        close = transformed.close

        def fail_close():
            close()
            raise OSError("close failed")

        monkeypatch.setattr(transformed, "close", fail_close)
        context.replace_image(transformed)
        if processing_error:
            raise processing_error
    result, accepted = context.outcome()
    expected = ImageErrorReason.ENCODE_FAILED if processing_error else ImageErrorReason.READ_ERROR
    assert result.error == expected and not result.success and result.skip is None and accepted is None
    assert source.closed and result.new_image.size == (40, 25)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_interrupt_propagates_after_cleanup(content, interrupt):
    with pytest.raises(interrupt):
        with ImageProcessingContext() as context:
            context.open_bytes_as_image(content)
            source = context.image.fp
            raise interrupt
    assert source.closed and context._image is None


def test_no_operation_is_a_skip_and_calls_are_independent(content):
    with ImageProcessingContext() as first:
        first.open_bytes_as_image(content)
    with ImageProcessingContext() as second:
        second.open_bytes_as_image(content)
        second.verify(lambda context: ImageSkipReason.SMALL_IMAGE)
        pytest.fail("A failed verification must stop the block")
    assert first.outcome()[0].skip == ImageSkipReason.NOT_OPTIMIZED
    assert second.outcome()[0].skip == ImageSkipReason.SMALL_IMAGE
    assert first.outcome()[0].error is second.outcome()[0].error is None
    assert first.original_image_info is not second.original_image_info


def test_cleanup_failure_overrides_skip(content):
    def fail():
        raise OSError("cleanup failed")

    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        context.exit_stack.callback(fail)
        context.verify(lambda context: ImageSkipReason.SMALL_IMAGE)
    result, accepted = context.outcome()
    assert result.error == ImageErrorReason.READ_ERROR and result.skip is None and accepted is None


def test_replacement_is_owned_even_if_previous_close_fails(content, monkeypatch):
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        original = context.image
        close = original.close
        replacement = original.resize((40, 25))

        def fail_close():
            close()
            raise OSError("old image close failed")

        monkeypatch.setattr(original, "close", fail_close)
        context.replace_image(replacement)
    assert context.outcome()[0].error == ImageErrorReason.READ_ERROR
    assert_closed(replacement)


@pytest.mark.parametrize("body_interrupt", [False, True])
def test_cleanup_does_not_swallow_interrupt(content, monkeypatch, body_interrupt):
    with pytest.raises(KeyboardInterrupt):
        with ImageProcessingContext() as context:
            context.open_bytes_as_image(content)
            source = context.image.fp
            transformed = context.image.resize((40, 25))
            close = transformed.close

            def fail_close():
                close()
                if body_interrupt:
                    raise OSError("cleanup failed")
                raise KeyboardInterrupt

            monkeypatch.setattr(transformed, "close", fail_close)
            context.replace_image(transformed)
            if body_interrupt:
                raise KeyboardInterrupt
            raise ValueError("processing failed")
    assert source.closed and context.candidate is None and context._image is None
