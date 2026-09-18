import io
import struct
import zipfile
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest

from library.epub.resources import Resource
from library.epub.sink import EpubZipSink
from library.zip import ZipSink


@pytest.mark.parametrize("chunks", [[], [b"", b"one", b"", b"two", b""]])
def test_chunks_round_trip_on_disk(tmp_path, chunks):
    path = tmp_path / "out.zip"
    with ZipSink(path) as sink:
        sink.write_chunks("data", (chunk for chunk in chunks))
    with ZipFile(path) as archive:
        assert archive.read("data") == b"".join(chunks)
        assert archive.getinfo("data").compress_type == ZIP_DEFLATED
        assert archive.testzip() is None


def test_unknown_size_uses_zip64(tmp_path, monkeypatch):
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 100)
    path = tmp_path / "out.zip"
    with ZipSink(path) as sink:
        sink.write_chunks("data", (b"x" * 40 for _ in range(5)))
    with ZipFile(path) as archive:
        assert archive.read("data") == b"x" * 200


class BoundedStream(io.BytesIO):
    def read(self, size=-1):
        assert 0 < size <= 65536
        return super().read(size)

    def seek(self, *args):
        raise AssertionError("Input must not be sought")


def test_stream_is_bounded_and_caller_owned():
    stream = BoundedStream(b"skip" + b"x" * 140000)
    stream.read(4)
    output = io.BytesIO()
    info = ZipInfo("data", date_time=(2020, 1, 2, 3, 4, 6))
    info.comment = b"comment"
    with ZipSink(output) as sink:
        sink.write_stream(info, stream)
    assert not stream.closed
    assert not output.closed
    assert info.file_size == 0
    with ZipFile(output) as archive:
        assert archive.read("data") == b"x" * 140000
        written = archive.getinfo("data")
        assert written.date_time == info.date_time
        assert written.comment == info.comment
        assert written.compress_type == ZIP_STORED


def test_failure_closes_entry_and_archive():
    def chunks():
        yield b"partial"
        raise RuntimeError("source failed")

    output = io.BytesIO()
    sink = ZipSink(output)
    with pytest.raises(RuntimeError, match="source failed"):
        with sink:
            sink.write_chunks("data", chunks())
    with pytest.raises(ValueError):
        _ = sink.zip_file
    with ZipFile(output) as archive:
        assert archive.read("data") == b"partial"


@pytest.mark.parametrize("size", [0, -1])
def test_invalid_chunk_size(size):
    with ZipSink(io.BytesIO()) as sink:
        with pytest.raises(ValueError, match="chunk_size"):
            sink.write_stream("data", io.BytesIO(b"content"), chunk_size=size)
        assert sink.zip_file.namelist() == []


@pytest.mark.parametrize("stream_resources", [False, True])
def test_epub_resources_keep_compression_rules(stream_resources):
    output = io.BytesIO()
    resources = [
        Resource.from_bytes("mimetype", b"application/epub+zip"),
        Resource(
            ZipInfo("chapter.xhtml"),
            stream_bytes=lambda _: (BoundedStream if stream_resources else io.BytesIO)(b"text" * 40000),
        ),
        Resource.from_bytes("image.png", b"image"),
    ]
    with EpubZipSink(output, stream_resources=stream_resources) as sink:
        for resource in resources:
            sink.write_resource(resource)
    assert (resources[1]._content is None) == stream_resources
    with ZipFile(output) as archive:
        assert archive.namelist()[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == ZIP_STORED
        assert archive.getinfo("image.png").compress_type == ZIP_STORED
        assert archive.getinfo("chapter.xhtml").compress_type == ZIP_DEFLATED
        assert archive.read("chapter.xhtml") == b"text" * 40000
    # Check the local header; ZIP64 extra fields need not appear in the directory.
    assert struct.unpack_from("<H", output.getvalue(), 28)[0] == 0


def test_epub_default_loads_and_caches_content():
    reads = []

    def source(info):
        reads.append(info.filename)
        return io.BytesIO(b"original")

    resource = Resource(ZipInfo("chapter.xhtml"), stream_bytes=source)
    output = io.BytesIO()
    with EpubZipSink(output) as sink:
        sink.write_resource(resource)
    assert reads == ["chapter.xhtml"]
    assert resource.content == b"original"
    assert reads == ["chapter.xhtml"]  # Export populated the cache.
    with ZipFile(output) as archive:
        assert archive.read("chapter.xhtml") == b"original"
        assert archive.getinfo("chapter.xhtml").extract_version == 20
    assert struct.unpack_from("<H", output.getvalue(), 28)[0] == 0


@pytest.mark.parametrize("stream_resources", [False, True])
@pytest.mark.parametrize("edited_content", [b"edited chapter", b""])
def test_epub_export_preserves_content_and_metadata_edits(stream_resources, edited_content):
    def source(info):
        raise AssertionError("Export must use edited content, not reopen the source")

    resource = Resource(ZipInfo("original.xhtml"), stream_bytes=source)
    resource.content = edited_content
    resource.filename = "text/renamed.xhtml"
    resource.info.date_time = (2022, 3, 4, 5, 6, 8)
    resource.info.comment = b"edited metadata"
    output = io.BytesIO()
    with EpubZipSink(output, stream_resources=stream_resources) as sink:
        sink.write_resource(resource)
    with ZipFile(output) as archive:
        assert archive.namelist() == ["text/renamed.xhtml"]
        assert archive.read(resource.filename) == edited_content
        written = archive.getinfo(resource.filename)
        assert written.date_time == resource.info.date_time
        assert written.comment == b"edited metadata"
