from pathlib import Path

import pytest

from library.epub.epub import EPUB


@pytest.fixture(
    params=[
        "C:/Users/Ivan/Projects/ewa/library/tests/samples/source/archive.zip",
        "C:/Users/Ivan/Projects/ewa/library/tests/samples/source/directory",
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
    EPUB(epub_path).package_into(destination)
