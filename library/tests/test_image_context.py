from dataclasses import replace
from io import BytesIO
import pickle

import pytest
from PIL import Image

from library.image.constants import ImageFormat, ImageMode
from library.image.context import ImageProcessingContext
from library.image.models import ImageErrorReason, ImageInfo, ImageSkipReason


@pytest.fixture
def content():
    with BytesIO() as buffer, Image.new("RGB", (20, 10), "red") as image:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def test_success_owns_input_and_transformed_images(content):
    with ImageProcessingContext(compression=80, min_filesize=0, max_dimensions=(0, 0)) as context:
        context.open_bytes_as_image(content)
        original = context._image
        source = original.fp
        transformed = original.resize((10, 5))
        context.replace_image(transformed)
        with pytest.raises(ValueError):
            original.getpixel((0, 0))
        with BytesIO() as output:
            transformed.save(output, format="PNG")
            context.candidate = output.getvalue()
        context.current_image_info.filesize = len(context.candidate)
        context.succeed()
    result, accepted = pickle.loads(pickle.dumps(context.outcome()))
    assert result.success and accepted
    assert result.original_image.size == (20, 10)
    assert result.new_image.size == (10, 5)
    assert source.closed and context._image is None
    for image in (original, transformed):
        with pytest.raises(ValueError):
            image.getpixel((0, 0))
    assert context.compression == 80 and context.min_filesize == 0 and context.max_dimensions == (0, 0)


def test_invalid_input_retains_size():
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(b"invalid image")
        pytest.fail("Opening failure must stop the block")
    result, accepted = context.outcome()
    assert result.error == ImageErrorReason.DECODE_FAILED
    assert result.original_image == ImageInfo.failed(filesize=13)
    assert accepted is None


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


def test_metadata_copies_separate_planning_from_working_image(content):
    with ImageProcessingContext(target_quality=70) as context:
        context.open_bytes_as_image(content)
        original = context.original_image_info
        current = context.current_image_info
        target = context.target_image_info
        assert original == current == target
        assert len({id(original), id(current), id(target)}) == 3
        target.size = (10, 5)
        target.mode = ImageMode.L
        target.format = ImageFormat.JPEG
        assert context.image.size == original.size == current.size == (20, 10)
        assert context.image.mode == original.mode == current.mode == "RGB"
        assert original.format == current.format == "PNG"

        context.replace_image(context.image.resize(target.size))
        assert current.size == target.size
        assert original.size == (20, 10)
        context.replace_image(context.image.convert(target.mode))
        assert current.mode == target.mode
        assert original.mode == "RGB"
        # Encoded properties change only after saving.
        assert current.format == "PNG" and current.filesize == len(content)
        assert target.filesize == original.filesize == len(content)
        assert context.target_quality == 70
        context.skip(ImageSkipReason.NOT_OPTIMIZED)
    assert context.outcome()[0].new_image is None


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
    assert result.error == ImageErrorReason.UNKNOWN
    assert result.original_image.filesize == len(content)
    assert opened[0][1].closed and accepted is None
    with pytest.raises(ValueError):
        opened[0][0].load()


@pytest.mark.parametrize(
    "error,reason",
    [(MemoryError(), ImageErrorReason.TOO_LARGE), (ValueError("encoder failed"), ImageErrorReason.ENCODE_FAILED)],
)
def test_processing_failure_retains_metadata(content, error, reason):
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        context.current_image_info = replace(context.current_image_info, filesize=1)
        context.candidate = b"candidate"
        raise error
    result, accepted = context.outcome()
    assert result.error == reason and result.original_image.size == (20, 10)
    assert result.new_image.filesize == 1 and accepted is None and context.candidate is None


def test_skip_stops_block_and_retains_candidate_metadata(content):
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        context.current_image_info = replace(context.current_image_info, filesize=999)
        context.candidate = b"rejected"
        context.skip(ImageSkipReason.WORSE_CONVERSION)
        pytest.fail("Skip must stop the block")
    result, accepted = context.outcome()
    assert result.skip == ImageSkipReason.WORSE_CONVERSION and result.error is None
    assert result.new_image.filesize == 999 and accepted is None


@pytest.mark.parametrize("processing_error", [None, ValueError("encoder failed")])
def test_cleanup_failure_closes_remaining_resources(content, monkeypatch, processing_error):
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        source = context._image.fp
        image = context._image
        transformed = image.copy()
        close = transformed.close

        def fail_close():
            close()
            raise OSError("close failed")

        monkeypatch.setattr(transformed, "close", fail_close)
        context.replace_image(transformed)
        context.candidate = b"encoded"
        context.current_image_info = replace(context.current_image_info, filesize=7)
        context.succeed()
        if processing_error:
            raise processing_error
    result, accepted = context.outcome()
    expected = ImageErrorReason.ENCODE_FAILED if processing_error else ImageErrorReason.READ_ERROR
    assert result.error == expected and not result.success and accepted is None
    assert source.closed and result.original_image.size == (20, 10)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_interrupt_propagates_after_cleanup(content, interrupt):
    with pytest.raises(interrupt):
        with ImageProcessingContext() as context:
            context.open_bytes_as_image(content)
            source = context._image.fp
            raise interrupt
    assert source.closed and context._image is None


def test_missing_completion_and_independent_calls(content):
    with ImageProcessingContext() as first:
        first.open_bytes_as_image(content)
    with ImageProcessingContext() as second:
        second.open_bytes_as_image(content)
        second.skip(ImageSkipReason.SMALL_IMAGE)
    assert first.outcome()[0].error == ImageErrorReason.UNKNOWN
    assert second.outcome()[0].skip == ImageSkipReason.SMALL_IMAGE
    assert first.original_image_info is not second.original_image_info


def test_success_requires_candidate(content):
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        context.succeed()
    assert context.outcome()[0].error == ImageErrorReason.UNKNOWN


def test_replacement_is_owned_even_if_previous_close_fails(content, monkeypatch):
    with ImageProcessingContext() as context:
        context.open_bytes_as_image(content)
        original = context._image
        close = original.close
        replacement = original.copy()

        def fail_close():
            close()
            raise OSError("old image close failed")

        monkeypatch.setattr(original, "close", fail_close)
        context.replace_image(replacement)
    assert context.outcome()[0].error == ImageErrorReason.READ_ERROR
    with pytest.raises(ValueError):
        replacement.getpixel((0, 0))


@pytest.mark.parametrize("body_interrupt", [False, True])
def test_cleanup_does_not_swallow_interrupt(content, monkeypatch, body_interrupt):
    with pytest.raises(KeyboardInterrupt):
        with ImageProcessingContext() as context:
            context.open_bytes_as_image(content)
            source = context._image.fp
            transformed = context._image.copy()
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
    assert source.closed and context.result is None
