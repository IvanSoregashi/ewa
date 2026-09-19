from io import BytesIO
from zipfile import ZipInfo
import pytest
from PIL import Image
from epub.recipe_image import perform_image_optimization
from library.epub.resources import Resource
from library.image.constants import ImageFormat, ImageMode, MEDIUM_WIDTH_SIZE
from library.image.models import ImageErrorReason
from library.test_utils.utils_image import counted_resource, generate_image


def test_optimization_skips_small_images():
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGB, (64, 32), noise=True)
    resource, _ = counted_resource(image_bytes, filename)
    original_content = resource.content

    result = perform_image_optimization(resource)

    assert result.success is False
    assert result.skip is not None
    assert result.error is None
    assert result.new_image is None
    assert result.original_image.size == (64, 32)
    assert resource.content == original_content  # untouched
    assert resource.filename == filename


def test_optimization_resizes_large_jpeg():
    image_bytes, filename = generate_image(ImageFormat.JPEG, ImageMode.RGB, (1500, 1500), noise=True)
    resource, _ = counted_resource(image_bytes, filename)
    original_content = resource.content

    result = perform_image_optimization(resource)

    assert result.success is True
    assert result.new_image is not None
    assert result.skip is None
    assert result.original_image.format is ImageFormat.JPEG
    assert result.new_image.size == (MEDIUM_WIDTH_SIZE[0], 1080)  # 1500 -> 1080 wide, height scaled
    assert resource.content != original_content

    with Image.open(BytesIO(resource.content)) as optimized:
        assert optimized.format == "JPEG"
        assert optimized.size == result.new_image.size
    assert resource.filename == filename  # no rename for jpeg


def test_optimization_converts_png_to_jpeg():
    """Noisy RGB PNG above the size threshold: inefficient bpp -> converted to JPEG."""
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGB, (1500, 1500), noise=True)
    resource, _ = counted_resource(image_bytes, filename)
    assert resource.content and len(resource.content) >= 50 * 1024  # guard: actually above threshold

    result = perform_image_optimization(resource)

    assert result.success is True
    assert result.new_image is not None
    assert result.original_image.format is ImageFormat.PNG
    assert result.new_image.format is ImageFormat.JPEG
    assert result.new_image.mode is ImageMode.RGB
    assert result.new_image.size == (MEDIUM_WIDTH_SIZE[0], 1080)

    # png -> jpg rename happened on the resource, media_type re-derived
    assert resource.filename.endswith(".jpg")
    assert resource.media_type == "image/jpeg"

    with Image.open(BytesIO(resource.content)) as optimized:
        assert optimized.format == "JPEG"


def test_optimization_resized_rgba_png_stays_png():
    """Real (random) alpha channel: no useless-transparency drop, no conversion - only resize."""
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGBA, (1500, 1500), noise=True)
    resource, _ = counted_resource(image_bytes, filename)
    assert len(resource.content) >= 50 * 1024

    result = perform_image_optimization(resource)

    assert result.success is True
    assert result.new_image is not None
    assert result.new_image.format is ImageFormat.PNG  # stays png
    assert result.new_image.mode is ImageMode.RGBA
    assert result.new_image.size == (MEDIUM_WIDTH_SIZE[0], 1080)
    assert resource.filename == filename  # no rename

    with Image.open(BytesIO(resource.content)) as optimized:
        assert optimized.format == "PNG"
        assert optimized.mode == "RGBA"


def test_optimization_drops_useless_transparency_and_stays_png():
    """Solid RGBA (fully opaque) above the size threshold: extra-efficient -> EXTRA resize,
    useless alpha dropped (RGBA -> RGB), format stays PNG, no rename."""
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGBA, (4000, 4000), noise=False)
    resource, _ = counted_resource(image_bytes, filename)
    assert len(resource.content) >= 50 * 1024  # 70KB in practice: above the skip threshold

    result = perform_image_optimization(resource)

    assert result.success is True
    assert result.new_image is not None
    assert result.original_image.mode is ImageMode.RGBA
    assert result.new_image.mode is ImageMode.RGB  # useless transparency dropped
    assert result.new_image.format is ImageFormat.PNG  # efficient bpp -> no conversion
    assert result.new_image.size == (2560, 2560)  # extra-efficient -> EXTRA_WIDTH_SIZE

    with Image.open(BytesIO(resource.content)) as optimized:
        assert optimized.mode == "RGB"
        assert optimized.size == result.new_image.size
    assert resource.filename == filename  # no rename: png stayed png


def test_optimization_noisy_opaque_rgba_drops_alpha_and_converts():
    """Noisy pixels with forced-opaque alpha: transparency is useless -> RGB -> JPEG conversion + rename."""
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGBA, (1500, 1500), noise=True, alpha=255)
    resource, _ = counted_resource(image_bytes, filename)
    assert len(resource.content) >= 50 * 1024

    result = perform_image_optimization(resource)

    assert result.success is True
    assert result.new_image is not None
    assert result.original_image.mode is ImageMode.RGBA
    assert result.new_image.mode is ImageMode.RGB  # forced-opaque alpha recognized as useless
    assert result.new_image.format is ImageFormat.JPEG
    assert resource.filename.endswith(".jpg")
    assert resource.media_type == "image/jpeg"


def test_optimization_result_is_reportable():
    """The result must be plain data (picklable across processes) with full before/after info."""
    image_bytes, filename = generate_image(ImageFormat.JPEG, ImageMode.RGB, (1500, 1500), noise=True)
    resource, _ = counted_resource(image_bytes, filename)

    result = perform_image_optimization(resource)

    as_dict = result.as_dict()
    assert as_dict["original_image"]["size"] == (1500, 1500)
    assert as_dict["new_image"]["size"][0] == MEDIUM_WIDTH_SIZE[0]
    assert as_dict["success"] is True


@pytest.mark.parametrize(
    "archive_path",
    ["pic.png", "OEBPS/pic.png", "OEBPS/images/pic.png", "OEBPS/deep/nested/dir/pic.png", "OEBPS/v2.dir/pic.png"],
)
def test_rename_png_to_jpg_with_archive_paths(archive_path):
    """The rename must only touch the final suffix and keep posix separators -
    str(Path(...)) on Windows would emit backslashes and corrupt the archive path."""
    image_bytes, _ = generate_image(ImageFormat.PNG, ImageMode.RGB, (1500, 1500), noise=True)
    resource, _ = counted_resource(image_bytes, archive_path)
    assert len(resource.content) >= 50 * 1024

    result = perform_image_optimization(resource)

    assert result.new_image is not None
    assert result.new_image.path is not None
    expected = archive_path.removesuffix(".png") + ".jpg"
    assert result.new_image.format is ImageFormat.JPEG  # ensure the rename branch is taken

    assert "\\" not in result.new_image.path
    assert result.new_image.path == expected
    assert resource.filename == expected
    assert resource.media_type == "image/jpeg"

    # bookkeeping: original path captured before the rename
    assert result.original_image.path == archive_path
    assert result.original_image.format is ImageFormat.PNG


def test_rename_keeps_stem_with_multiple_dots():
    image_bytes, _ = generate_image(ImageFormat.PNG, ImageMode.RGB, (1500, 1500), noise=True)
    resource, _ = counted_resource(image_bytes, "OEBPS/images/pic.final.png")

    result = perform_image_optimization(resource)

    assert result.new_image is not None
    assert result.new_image.format is ImageFormat.JPEG
    assert result.new_image.path == "OEBPS/images/pic.final.jpg"
    assert resource.media_type == "image/jpeg"


def test_no_rename_when_png_stays_png():
    """Extra-efficient RGBA resize keeps the png format - path and media_type untouched."""
    image_bytes, _ = generate_image(ImageFormat.PNG, ImageMode.RGBA, (4000, 4000), noise=False)
    resource, _ = counted_resource(image_bytes, "OEBPS/images/solid.png")

    result = perform_image_optimization(resource)

    assert result.success is True
    assert result.new_image is not None
    assert result.new_image.format is ImageFormat.PNG
    assert result.new_image.path is None  # rename branch never ran
    assert resource.filename == "OEBPS/images/solid.png"
    assert resource.media_type == "image/png"


def test_perform_optimization_garbage_payload_returns_error_result():
    """Bytes that Image.open rejects entirely (before optimization_machine)."""
    resource, _ = counted_resource(b"this is not an image" * 100, "OEBPS/images/garbage.png")

    result = perform_image_optimization(resource)

    assert result.success is False
    assert result.error == ImageErrorReason.DECODE_FAILED
    assert result.new_image is None
    info = result.original_image
    assert info.size == (0, 0)
    assert info.filesize == resource.info.file_size
    assert info.path == "OEBPS/images/garbage.png"
    assert info.format == "UNKNOWN"
    assert info.mode == "UNKNOWN"


def test_perform_optimization_source_read_failure_returns_read_error():
    """stream_bytes itself explodes (corrupt zip member, vanished file) -> READ_ERROR."""
    info = ZipInfo("OEBPS/images/unreadable.png")
    info.file_size = 1234

    def broken_stream(zip_info: ZipInfo):
        raise OSError("image file is truncated or source vanished")

    resource = Resource(info=info, stream_bytes=broken_stream)

    result = perform_image_optimization(resource)

    assert result.success is False
    assert result.error == ImageErrorReason.READ_ERROR
    assert result.original_image.size == (0, 0)
    assert result.original_image.filesize == 1234
    assert result.original_image.path == "OEBPS/images/unreadable.png"
    assert result.original_image.format == "UNKNOWN"
