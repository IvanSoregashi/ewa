"""Coverage for library.epub.image_recipe: get_image_info, get_image_info_with_extrema, perform_image_optimization.

All images are generated on the fly (no repo fixtures). Read-accounting lives
entirely in this file: Resource accepts an injected stream_bytes callable, which
is all we need to count what the reader actually pulls through.
"""

import io
import random
from collections.abc import Callable, Iterator
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from zipfile import ZipInfo

import pytest
from PIL import Image

from library.epub.recipe_image import get_image_info, get_image_info_with_extrema, perform_image_optimization
from library.epub.resources import Resource
from library.image.constants import ImageFormat, ImageMode, MEDIUM_WIDTH_SIZE
from library.image.models import ImageInfo, ImageErrorReason, ImageSkipReason
from library.image.optimization import optimization_machine

images_dir = Path(__file__).parent / "samples" / "images"

COMBOS = [
    (ImageFormat.PNG, ImageMode.RGB),
    (ImageFormat.PNG, ImageMode.RGBA),
    (ImageFormat.JPEG, ImageMode.RGB),
]
COMBO_IDS = ["png-rgb", "png-rgba", "jpeg-rgb"]


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


# ---------------------------------------------------------------------------
# ImageInfo.from_image must never fail on an image that opened fine
# ---------------------------------------------------------------------------


def test_from_image_accepts_unknown_pillow_format_and_mode():
    """16-bit grayscale PNG opens as mode 'I;16'; cameras produce 'MPO' format -
    neither is in the core enums, but from_image must still work."""
    buffer = BytesIO()
    Image.new("I;16", (4, 4), 7).save(buffer, format="PNG")
    with Image.open(BytesIO(buffer.getvalue())) as image:
        info = ImageInfo.from_image(image, filesize=100)
    assert info.mode == ImageMode("I;16")
    assert info.format is ImageFormat.PNG

    mpo_image = Image.new("RGB", (2, 2))
    mpo_image.format = "MPO"
    info_mpo = ImageInfo.from_image(mpo_image, filesize=100)
    assert info_mpo.format == ImageFormat("MPO")

    # ad-hoc members are stable singletons afterwards
    assert ImageMode("I;16") is ImageMode("I;16")
    assert ImageFormat("MPO") is ImageFormat("MPO")


def test_from_image_extracts_header_extras_static():
    buffer = BytesIO()
    Image.new("RGBA", (32, 16), (255, 0, 0, 128)).save(buffer, format="PNG")
    with Image.open(BytesIO(buffer.getvalue())) as image:
        info = ImageInfo.from_image(image, filesize=len(buffer.getvalue()))

    assert info.is_animated is False
    assert info.n_frames == 1
    assert info.has_transparency_data is True
    assert info.progressive is None or info.progressive is False
    assert info.has_icc_profile is False


def test_from_image_extracts_jpeg_markers():
    buffer = BytesIO()
    image = Image.new("RGB", (64, 64), "green")
    image.save(buffer, format="JPEG", quality=90, dpi=(300, 300), progressive=True, icc_profile=b"fake-icc")
    with Image.open(BytesIO(buffer.getvalue())) as jpeg:
        info = ImageInfo.from_image(jpeg, filesize=len(buffer.getvalue()))

    assert info.progressive is True
    assert info.dpi is not None and round(info.dpi[0]) == 300
    assert info.has_icc_profile is True
    assert info.is_animated is False


def test_from_image_extracts_animation():
    """A real two-frame animated GIF."""
    buffer = BytesIO()
    frame_a = Image.new("RGB", (16, 16), "red")
    frame_b = Image.new("RGB", (16, 16), "blue")
    frame_a.save(buffer, format="GIF", save_all=True, append_images=[frame_b], duration=100, loop=0)
    with Image.open(BytesIO(buffer.getvalue())) as image:
        info = ImageInfo.from_image(image, filesize=len(buffer.getvalue()))

    assert info.is_animated is True
    assert info.n_frames == 2


# ---------------------------------------------------------------------------
# get_image_info
# ---------------------------------------------------------------------------


@pytest.fixture(params=COMBOS, ids=COMBO_IDS)
def combo(request) -> tuple[ImageFormat, ImageMode]:
    return request.param


def test_get_image_info_reports_correct_metadata(combo):
    image_format, mode = combo
    size = (64, 32)
    image_bytes, filename = generate_image(image_format, mode, size, noise=True)
    resource, _ = counted_resource(image_bytes, filename)

    info = get_image_info(resource)

    assert info.size == size
    assert info.format is image_format
    assert info.mode is mode
    assert info.filesize == len(image_bytes)
    assert info.extrema is None


def test_get_image_info_is_lazy(combo):
    """Opening must only ever pull the header, never pixel data."""
    image_format, mode = combo
    size = (1000, 1000)
    image_bytes, filename = generate_image(image_format, mode, size, noise=True)
    resource, total_served = counted_resource(image_bytes, filename)

    for _ in range(3):  # repeated opens must stay cheap too
        info = get_image_info(resource)
        assert info.size == size

    assert total_served() < len(image_bytes) * 0.1, f"read {total_served()} of {len(image_bytes)} bytes"


def test_get_image_info_full_read_is_counted_exactly():
    """Control for the accounting: eager consumption registers byte-exactly."""
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGB, (1000, 1000), noise=True)
    resource, total_served = counted_resource(image_bytes, filename)

    assert len(resource.content) == len(image_bytes)
    assert total_served() == len(image_bytes)


def test_get_image_info_stays_lazy_for_huge_jpeg():
    buffer = BytesIO()
    Image.new("RGB", (4000, 4000), "blue").save(buffer, format="JPEG", quality=95)
    resource, total_served = counted_resource(buffer.getvalue(), "big.jpg")

    info = get_image_info(resource)

    assert info.size == (4000, 4000)
    assert total_served() < 8192, f"read {total_served()} bytes of a 4000x4000 JPEG header"


# ---------------------------------------------------------------------------
# get_image_info_with_extrema
# ---------------------------------------------------------------------------


def test_extrema_computed_for_rgba():
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGBA, (100, 100), noise=True)
    resource, _ = counted_resource(image_bytes, filename)

    info = get_image_info_with_extrema(resource)

    assert info.mode is ImageMode.RGBA
    assert info.extrema is not None
    assert len(info.extrema) == 4
    # noisy pixels: every channel spans the full range
    for low, high in info.extrema:
        assert low == 0
        assert high == 255


def test_extrema_solid_rgba_is_deterministic():
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGBA, (10, 10), noise=False)
    resource, _ = counted_resource(image_bytes, filename)

    info = get_image_info_with_extrema(resource)

    red, green, blue, alpha = info.extrema
    assert red == (255, 255)  # solid red fill
    assert green == (0, 0)
    assert blue == (0, 0)
    assert alpha == (255, 255)


def test_extrema_skipped_for_rgb():
    for image_format in (ImageFormat.PNG, ImageFormat.JPEG):
        image_bytes, filename = generate_image(image_format, ImageMode.RGB, (100, 100), noise=True)
        resource, total_served = counted_resource(image_bytes, filename)

        info = get_image_info_with_extrema(resource)

        assert info.extrema is None
        assert total_served() < len(image_bytes) * 0.1, "RGB path must not load pixel data"


def test_extrema_rgba_loads_full_content():
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGBA, (100, 100), noise=True)
    resource, total_served = counted_resource(image_bytes, filename)

    get_image_info_with_extrema(resource)

    # full content read, plus the small header read from get_image_info
    assert total_served() >= len(image_bytes), "RGBA extrema path is expected to be eager"


# ---------------------------------------------------------------------------
# perform_image_optimization
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# png -> jpg rename with archive-style paths
# ---------------------------------------------------------------------------


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

    assert result.new_image.format is ImageFormat.JPEG
    assert result.new_image.path == "OEBPS/images/pic.final.jpg"
    assert resource.media_type == "image/jpeg"


def test_no_rename_when_png_stays_png():
    """Extra-efficient RGBA resize keeps the png format - path and media_type untouched."""
    image_bytes, _ = generate_image(ImageFormat.PNG, ImageMode.RGBA, (4000, 4000), noise=False)
    resource, _ = counted_resource(image_bytes, "OEBPS/images/solid.png")

    result = perform_image_optimization(resource)

    assert result.success is True
    assert result.new_image.format is ImageFormat.PNG
    assert result.new_image.path is None  # rename branch never ran
    assert resource.filename == "OEBPS/images/solid.png"
    assert resource.media_type == "image/png"


# ---------------------------------------------------------------------------
# perform_image_optimization must never raise - pre-machine failures included
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# real-file sanity
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def image_on_disk() -> Iterator[Path]:
    """A generated image written to the real images dir; removed after the session."""
    images_dir.mkdir(parents=True, exist_ok=True)
    image_bytes, filename = generate_image(ImageFormat.PNG, ImageMode.RGB, (1000, 1000), noise=True)
    path = images_dir / filename
    path.write_bytes(image_bytes)
    yield path
    path.unlink(missing_ok=True)


def counted_disk_resource(path: Path) -> tuple[Resource, Callable[[], int]]:
    """Resource over a real file on disk, with read accounting on fresh handles."""
    info = ZipInfo.from_file(path)

    streams: list[CountingReader] = []

    def stream_bytes(zip_info: ZipInfo) -> CountingReader:
        stream = CountingReader(path.open("rb"))  # fresh handle per stream() call
        streams.append(stream)
        return stream

    def total_served() -> int:
        return sum(s.served for s in streams)

    return Resource(info=info, stream_bytes=stream_bytes), total_served


def test_real_file_reads_stay_lazy(image_on_disk: Path):
    """Sanity against a real file on disk: header ops stay cheap, full read is exact."""
    resource, total_served = counted_disk_resource(image_on_disk)

    first = get_image_info(resource)
    lazy_served = total_served()
    second = get_image_info(resource)

    assert first.size == second.size == (1000, 1000)
    lazy_served = total_served()
    assert lazy_served == 114, f"header ops pulled {lazy_served} bytes"

    before_content = total_served()
    assert len(resource.content) == image_on_disk.stat().st_size
    # exactly the payload flows through for the eager read
    assert total_served() - before_content == image_on_disk.stat().st_size
