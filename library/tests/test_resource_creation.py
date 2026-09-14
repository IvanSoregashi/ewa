import io
from zipfile import ZipFile, ZipInfo

import pytest

from library.epub.resources import Resource, ResourceIndex
from library.epub.sink import EpubZipSink


@pytest.mark.parametrize("content", [b"", b"new chapter"])
def test_create_add_rename_and_export(content):
    resource = Resource.from_bytes(filename="chapter.xhtml", content=content)
    assert resource.info.file_size == len(content)
    assert resource.media_type == "application/xhtml+xml"
    index = ResourceIndex()
    index.add(resource)
    index.rename(resource, "text/chapter.xhtml")
    for _ in range(2):
        with resource.stream() as stream:
            assert stream.read() == content
    output = io.BytesIO()
    with EpubZipSink(output) as sink:
        for entry in index:
            sink.write_resource(entry)
    with ZipFile(output) as archive:
        assert archive.namelist() == ["text/chapter.xhtml"]
        assert archive.read("text/chapter.xhtml") == content


def test_source_factory_is_lazy_and_preserves_metadata():
    info = ZipInfo("old.txt", date_time=(2020, 1, 2, 3, 4, 6))
    info.file_size = 4
    info.compress_size = 3
    reads = []

    def read(entry):
        reads.append(entry.filename)
        return io.BytesIO(b"data")

    resource = Resource(info, stream_bytes=read)
    assert reads == []
    assert resource.info.date_time == info.date_time
    assert resource.info.compress_size == 3
    ResourceIndex.from_resource_list([resource]).rename(resource, "new.txt")
    assert resource.content == b"data"
    assert resource.content == b"data"
    assert reads == ["old.txt"]
    assert info.filename == "old.txt"


def test_filesystem_factory_reads_original_after_rename(tmp_path):
    path = tmp_path / "source.txt"
    path.write_bytes(b"on disk")
    resource = Resource.from_filesystem_path(path)
    ResourceIndex.from_resource_list([resource]).rename(resource, "output.txt")
    assert resource.content == b"on disk"
    assert path.read_bytes() == b"on disk"
