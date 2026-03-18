from datetime import datetime
from pathlib import Path

import pytest

from library.epub.epub import EPUB

ARCHIVE = "C:/Users/Ivan/Projects/ewa/library/tests/samples/source/archive.zip"
DIRECTORY = "C:/Users/Ivan/Projects/ewa/library/tests/samples/source/directory"
EPUB1 = "C:/Users/Ivan/Projects/ewa/library/tests/samples/source/a-monster-second-chance.epub"
DIRECTORY1 = "C:/Users/Ivan/Projects/ewa/library/tests/samples/source/a-monster-second-chance"


@pytest.fixture(
    params=[
        ARCHIVE,
        DIRECTORY,
    ],
    ids=["zipfile", "directory"],
)
def epub_path(request):
    return request.param


@pytest.fixture
def destination():
    destination = "test.epub"
    yield destination
    Path(destination).unlink()


def test_stream_copy(epub_path, destination):
    epub1 = EPUB(epub_path)
    epub1.package_into(destination)

    epub2 = EPUB(destination)

    with epub1.source.open(), epub2.source.open():
        infolist1 = sorted(filter(lambda x: not x.is_dir(), epub1.source.infolist()), key=lambda x: x.filename)
        infolist2 = sorted(filter(lambda x: not x.is_dir(), epub2.source.infolist()), key=lambda x: x.filename)
        for info1, info2 in zip(infolist1, infolist2):
            assert info1.filename == info2.filename
            assert info1.file_size == info2.file_size

            dt1 = datetime(*info1.date_time)
            dt2 = datetime(*info2.date_time)

            delta = abs((dt1 - dt2).total_seconds())
            assert delta <= 2, f"Timestamp drift too large: {dt1} vs {dt2}"

            if info1.is_dir():
                continue
            assert epub1.source.read_bytes(info1) == epub2.source.read_bytes(info2)


def test_archive_repackaging(destination):
    epub1 = EPUB(EPUB1)
    epub1.package_into(destination)
    epub2 = EPUB(destination)

    source1 = epub1.source
    source2 = epub2.source

    with source1.open(), source2.open():
        for info1, info2 in zip(source1.infolist(), source2.infolist()):
            assert info1.filename == info2.filename
            assert info1.file_size == info2.file_size
            assert info1.date_time == info2.date_time
            assert info1.is_dir() == info2.is_dir()
            assert info1.CRC == info2.CRC
            assert source1.read_bytes(info1) == source2.read_bytes(info2)


def test_directory_packaging(destination):
    epub1 = EPUB(EPUB1)
    EPUB(DIRECTORY1).package_into(destination)
    epub2 = EPUB(destination)

    source1 = epub1.source
    source2 = epub2.source
    print()
    with source1.open(), source2.open():
        source1.zip_file.printdir()
        source2.zip_file.printdir()
        assert len(source1.infolist()) == len(source2.infolist())
        for info1, info2 in zip(
            sorted(source1.infolist(), key=lambda x: x.filename), sorted(source2.infolist(), key=lambda x: x.filename)
        ):
            assert info1.filename == info2.filename
            assert info1.file_size == info2.file_size
            assert info1.date_time == info2.date_time
            assert info1.is_dir() == info2.is_dir()
            assert info1.CRC == info2.CRC
            assert source1.read_bytes(info1) == source2.read_bytes(info2)
