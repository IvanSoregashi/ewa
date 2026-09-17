from dataclasses import FrozenInstanceError
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from library.epub.epub import EPUB
from library.epub.media_type import FileName
from library.epub.verification import MimetypeVerification, ValidXMLChapters
from .test_verification import build_epub, BROKEN_CHAPTER, VALID_CHAPTER


def test_reuse_returns_independent_findings_without_book_analytics(tmp_path, monkeypatch):
    broken = tmp_path / "broken.epub"
    valid = tmp_path / "valid.epub"
    build_epub(broken, {"bad.xhtml": BROKEN_CHAPTER})
    build_epub(valid, {"good.xhtml": VALID_CHAPTER})

    def no_analytics(*args, **kwargs):
        raise AssertionError("Checks must not collect book analytics")

    monkeypatch.setattr(EPUB, "info", no_analytics)
    check = ValidXMLChapters()
    failure = check.verify(EPUB(broken))
    success = check.verify(EPUB(valid))
    assert not failure.passed and "bad.xhtml" in failure.details
    assert success.passed and success.details == ""
    assert not hasattr(check, "epub_info")
    with pytest.raises(FrozenInstanceError):
        failure.passed = True


def test_mimetype_check_handles_missing_compressed_and_valid(tmp_path):
    check = MimetypeVerification()
    path = tmp_path / "book.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("placeholder", b"")
    assert "not found" in check.verify(EPUB(path)).details
    with ZipFile(path, "w") as archive:
        archive.writestr(FileName.MIMETYPE, b"application/epub+zip", compress_type=ZIP_DEFLATED)
    assert "compressed" in check.verify(EPUB(path)).details
    build_epub(path, {})
    assert check.verify(EPUB(path)).passed
