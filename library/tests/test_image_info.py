"""Coverage for library.epub.image_info: get_image_info and get_image_info_with_extrema.

All images are generated on the fly (no repo fixtures). Read-accounting helpers
live in library.test_utils.utils_image and are shared with plugin tests.
"""

from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path
from zipfile import ZipInfo

import pytest
from PIL import Image

from library.epub.image_info import get_image_info, get_image_info_with_extrema
from library.epub.resources import Resource
from library.image.constants import ImageFormat, ImageMode
from library.image.models import ImageInfo
from library.test_utils.utils_image import CountingReader, counted_resource, generate_image

images_dir = Path(__file__).parent / "samples" / "images"

COMBOS = [
    (ImageFormat.PNG, ImageMode.RGB),
    (ImageFormat.PNG, ImageMode.RGBA),
    (ImageFormat.JPEG, ImageMode.RGB),
]
COMBO_IDS = ["png-rgb", "png-rgba", "jpeg-rgb"]


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


# ---------------------------------------------------------------------------
# png -> jpg rename with archive-style paths
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# perform_image_optimization must never raise - pre-machine failures included
# ---------------------------------------------------------------------------


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
