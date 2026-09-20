from pathlib import Path

import pytest
from PIL import Image

from library.epub.epub import EpubInfo
from library.image.constants import ImageFormat, ImageMode
from library.image.models import ImageInfo
from library.image.optimization import is_efficient, is_extra_efficient


def test_failed_image_retains_only_known_dimensions_and_density():
    info = ImageInfo.failed(path="broken.png", filesize=123)
    assert info.path == "broken.png"
    assert info.filesize == 123
    assert info.size is None
    assert info.width is None
    assert info.height is None
    assert info.bytes_per_pixel is None
    assert not is_efficient(info)
    assert not is_extra_efficient(info)


@pytest.mark.parametrize("size", [(0, 0), (0, 10), (10, 0)])
def test_old_zero_area_snapshots_have_no_density(size):
    info = ImageInfo(size=size, filesize=123, format="UNKNOWN", mode="UNKNOWN")
    assert info.bytes_per_pixel is None


def test_density_uses_bytes_and_preserves_zero_file_size():
    info = ImageInfo(size=(5, 10), filesize=100, format=ImageFormat.PNG, mode=ImageMode.RGB)
    assert info.width == 5
    assert info.height == 10
    assert info.bytes_per_pixel == 2
    info.filesize = 0
    assert info.bytes_per_pixel == 0


@pytest.mark.parametrize(
    "filesize, efficient, extra_efficient",
    [(19, True, True), (20, True, False), (49, True, False), (50, False, False)],
)
def test_optimizer_preserves_strict_density_thresholds(filesize, efficient, extra_efficient):
    info = ImageInfo(size=(10, 10), filesize=filesize, format=ImageFormat.PNG, mode=ImageMode.RGB)
    assert is_efficient(info) is efficient
    assert is_extra_efficient(info) is extra_efficient


@pytest.mark.parametrize("fail_read", [False, True])
def test_from_file_closes_image_even_when_reading_info_fails(tmp_path, monkeypatch, fail_read):
    path = tmp_path / "image.png"
    Image.new("RGB", (8, 16)).save(path)
    open_image = Image.open
    handles = []

    def track_open(file):
        image = open_image(file)
        handles.append(image.fp)
        return image

    monkeypatch.setattr(Image, "open", track_open)
    if fail_read:

        def fail_info(cls, **kwargs):
            raise ValueError("Cannot read metadata")

        monkeypatch.setattr(ImageInfo, "from_image", classmethod(fail_info))
        with pytest.raises(ValueError, match="Cannot read metadata"):
            ImageInfo.from_file(path)
    else:
        info = ImageInfo.from_file(path)
        assert info.size == (8, 16)
        assert info.filesize == path.stat().st_size
    assert len(handles) == 1
    assert handles[0].closed


def test_epub_from_path_reads_filesystem_info_without_parsing(tmp_path):
    path: Path = tmp_path / "unparsed.epub"
    path.write_bytes(b"Not a ZIP archive")
    info = EpubInfo.from_path(path)
    assert info.path == path
    assert info.path_size == len(b"Not a ZIP archive")
    assert info.total is None
    assert info.images is None
    assert info.htmls is None
    assert info.fonts is None
    assert info.identifier is None
    assert info.title is None
    assert info.author is None
