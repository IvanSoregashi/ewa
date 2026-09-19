import io
from zipfile import ZipFile, ZipInfo

import pytest

from library.epub.epub import EPUB
from library.epub.resources import Resource, ResourceIndex


@pytest.mark.parametrize("source_kind", ["zip", "directory"])
def test_rename_before_read_preserves_source_and_exports_new_name(tmp_path, source_kind):
    path = tmp_path / "input"
    if source_kind == "zip":
        with ZipFile(path, "w") as archive:
            archive.writestr("old.txt", b"original bytes")
    else:
        path.mkdir()
        (path / "old.txt").write_bytes(b"original bytes")
    epub = EPUB(path)
    resource = epub.resources.by_path("old.txt")
    assert resource is not None
    epub.resources.rename(resource, "new.txt")
    assert epub.resources.by_path("old.txt") is None
    assert epub.resources.by_path("new.txt") is resource
    with resource.stream() as stream:
        assert stream.read() == b"original bytes"
    epub.resources.rename(resource, "final.txt")
    output = io.BytesIO()
    epub.package_into(output)
    with ZipFile(output) as archive:
        assert archive.namelist() == ["final.txt"]
        assert archive.read("final.txt") == b"original bytes"
    assert epub.source.read_bytes("old.txt") == b"original bytes"


def make_resource(name):
    return Resource.from_bytes(name, b"data")


def test_rename_collision_and_foreign_resource_leave_index_unchanged():
    first, second = make_resource("one.png"), make_resource("two.jpg")
    index = ResourceIndex.from_resource_list([first, second])
    with pytest.raises(ValueError, match="already exists"):
        index.rename(first, "two.jpg")
    with pytest.raises(ValueError, match="not indexed"):
        index.rename(make_resource("one.png"), "three.jpg")
    assert index.by_path("one.png") is first
    assert index.by_path("two.jpg") is second
    assert first.filename == "one.png"
    assert list(index) == [first, second]
    index.rename(first, "one.png")
    index.rename(first, "one.jpg")
    assert first.media_type == "image/jpeg"
    assert index.by_path("one.jpg") is first


def test_output_metadata_does_not_mutate_original_zipinfo():
    info = ZipInfo("original.txt")
    observed = []

    def read(original):
        observed.append(original.filename)
        return io.BytesIO(b"original")

    resource = Resource(info, stream_bytes=read)
    index = ResourceIndex.from_resource_list([resource])
    index.rename(resource, "changed.txt")
    assert info.filename == "original.txt"
    assert resource.content == b"original"
    assert observed == ["original.txt"]
