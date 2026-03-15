from pathlib import Path
from zipfile import Path as ZipFilePath

import pytest

from library.epub.source import DirectorySource, SourceProtocol, ZipFileSource


SAMPLE_DIR = Path(__file__).parent / "samples" / "source"
DIRECTORY = SAMPLE_DIR / "directory"
ARCHIVE = SAMPLE_DIR / "archive.zip"
RELATIVE_NAMELIST = [
    "mimetype",
    "META-INF/",
    "META-INF/container.xml",
    "content.opf",
    "nav.xhtml",
    "cover.xhtml",
    "style/",
    "style/nav.css",
    "toc.ncx",
    "vol_0_ch_0_1_1.xhtml",
]
RELATIVE_FILE_NAMELIST = [
    "mimetype",
    "META-INF/container.xml",
    "content.opf",
    "nav.xhtml",
    "cover.xhtml",
    "style/nav.css",
    "toc.ncx",
    "vol_0_ch_0_1_1.xhtml",
]
FILESIZES = {
    "content.opf": 1187,
    "cover.xhtml": 405,
    "META-INF/": 0,
    "META-INF/container.xml": 251,
    "mimetype": 20,
    "nav.xhtml": 700,
    "style/": 0,
    "style/nav.css": 495,
    "toc.ncx": 1036,
    "vol_0_ch_0_1_1.xhtml": 6521,
}


@pytest.fixture(params=[DirectorySource(DIRECTORY), ZipFileSource(ARCHIVE)], ids=["DirectorySource", "ZipFileSource"])
def source(request: pytest.FixtureRequest) -> SourceProtocol:
    return request.param


@pytest.fixture(params=[Path(DIRECTORY), ZipFilePath(ARCHIVE)], ids=["DirectoryPath", "ZipFilePath"])
def path_source(request: pytest.FixtureRequest) -> ZipFilePath:
    return request.param


def test_custom_source(source):
    assert set(source.namelist()) == set(RELATIVE_NAMELIST)
    assert set(source.file_namelist()) == set(RELATIVE_FILE_NAMELIST)

    with source.open():
        set_namelist = set(Path(path.relative_to(source.root)) for path in source.pathlist())
        assert set_namelist == set(Path(path) for path in RELATIVE_NAMELIST)
        set_file_namelist = set(Path(path.relative_to(source.root)) for path in source.file_pathlist())
        assert set_file_namelist == set(Path(path) for path in RELATIVE_FILE_NAMELIST)

    assert source.read_text("mimetype") == "application/epub+zip"
    assert source.read_bytes("mimetype") == b"application/epub+zip"
    infolist = source.infolist()
    with source.open():
        with_infolist = source.infolist()
    for info1, info2 in zip(infolist, with_infolist):
        assert info1.filename == info2.filename
        assert info1.file_size == info2.file_size
        assert info1.date_time == info2.date_time
    for info in infolist:
        assert info.file_size == FILESIZES[info.filename]


def test_source_paths(source):
    with source.open():
        for path in source.file_pathlist():
            assert "ï¼Œ" not in path.read_text(encoding="utf-8")
            assert "ï¼Œ" not in source.read_text(path)
            assert source.read_bytes(path) == path.read_bytes()
            assert source.read_text(path) == path.read_text(encoding="utf-8")

        for path in source.file_namelist():
            assert source.read_bytes(path) == (DIRECTORY / path).read_bytes()
            assert source.read_text(path) == (DIRECTORY / path).read_text(encoding="utf-8")

        for path in source.infolist():
            if path.is_dir():
                continue
            assert source.read_bytes(path) == (DIRECTORY / path.filename).read_bytes()
            assert source.read_text(path) == (DIRECTORY / path.filename).read_text(encoding="utf-8")
