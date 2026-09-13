from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from library.epub.source import DirectorySource, ZipFileSource
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file


@pytest.fixture(params=["directory", "zip"])
def synthetic_source(request, tmp_path):
    info = ZipInfo("nested/chapter.xhtml", date_time=(2020, 2, 3, 4, 5, 6))
    content = b"<html>Chapter</html>"
    if request.param == "directory":
        root = tmp_path / "source"
        member = root / info.filename
        member.parent.mkdir(parents=True)
        member.write_bytes(content)
        apply_zipinfo_timestamp_to_file(info, member)
        return DirectorySource(root)
    archive_path = tmp_path / "source.epub"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/", b"")
        archive.writestr(info, content)
    return ZipFileSource(archive_path)


@pytest.mark.parametrize("destination_kind", ["directory", "new_file", "existing_file"])
@pytest.mark.parametrize("use_info", [False, True])
def test_extract_exact_destination(synthetic_source, tmp_path, destination_kind, use_info):
    source = synthetic_source
    member_name = "nested/chapter.xhtml"
    member = source.getinfo(member_name) if use_info else member_name
    output = tmp_path / "output"
    output.mkdir()
    if destination_kind == "directory":
        destination = output
        expected = output / "chapter.xhtml"
    else:
        destination = expected = output / "renamed.xhtml"
        if destination_kind == "existing_file":
            destination.write_bytes(b"old content")

    result = source.extract(destination, member)

    assert Path(result) == expected
    assert expected.read_bytes() == source.read_bytes(member_name)
    assert list(output.iterdir()) == [expected]
    assert ZipInfo.from_file(expected).date_time == source.getinfo(member_name).date_time


def test_extract_rejects_directory_member(synthetic_source, tmp_path):
    destination = tmp_path / "output"
    destination.mkdir()
    with pytest.raises(IsADirectoryError):
        synthetic_source.extract(destination, "nested/")
    assert list(destination.iterdir()) == []


def test_extract_requires_existing_parent(synthetic_source, tmp_path):
    with pytest.raises(FileNotFoundError):
        synthetic_source.extract(tmp_path / "missing" / "chapter.xhtml", "nested/chapter.xhtml")
    # An extraction failure must not leave the source unusable.
    assert synthetic_source.read_bytes("nested/chapter.xhtml") == b"<html>Chapter</html>"


@pytest.fixture
def zip_source(tmp_path):
    path = tmp_path / "book.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("chapter.xhtml", b"chapter")
    return ZipFileSource(path)


def test_zip_session_recovers_after_exception(zip_source):
    with pytest.raises(RuntimeError, match="processing failed"):
        with zip_source.open():
            handle = zip_source.zip_file
            raise RuntimeError("processing failed")
    assert handle.fp is None
    assert zip_source.read_bytes("chapter.xhtml") == b"chapter"


def test_nested_exception_does_not_close_outer_session(zip_source):
    with zip_source.open():
        handle = zip_source.zip_file
        with pytest.raises(RuntimeError):
            with zip_source.open():
                raise RuntimeError("inner failure")
        assert zip_source.zip_file is handle
        assert handle.fp is not None
        assert zip_source.read_bytes("chapter.xhtml") == b"chapter"
    assert handle.fp is None


def test_propagated_nested_exception_allows_reopening(zip_source):
    with pytest.raises(RuntimeError):
        with zip_source.open():
            with zip_source.open():
                raise RuntimeError("nested failure")
    assert zip_source.read_bytes("chapter.xhtml") == b"chapter"
