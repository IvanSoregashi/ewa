from pathlib import Path
from zipfile import ZipInfo, ZipFile, Path as ZipFilePath

import pytest

from library.epub.source import DirectorySource, DirectorySink, SourceProtocol
from library.epub.epub import SourceDirectory, SourceZipFile, SourceProtocol as SSourceProtocol


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


@pytest.fixture(params=[DirectorySource(DIRECTORY), ZipFile(ARCHIVE)], ids=["DirectorySource", "ZipFile"])
def source_epublib(request: pytest.FixtureRequest) -> SourceProtocol:
    return request.param

@pytest.fixture(params=[Path(DIRECTORY), ZipFilePath(ARCHIVE)], ids=["DirectoryPath", "ZipFilePath"])
def path_source(request: pytest.FixtureRequest) -> ZipFilePath:
    return request.param


@pytest.fixture(params=[SourceDirectory(DIRECTORY), SourceZipFile(ARCHIVE)], ids=["SourceDirectory", "SourceZipFile"])
def custom_source(request: pytest.FixtureRequest) -> SSourceProtocol:
    return request.param


def test_iterate(source_epublib):
    print()
    for info in source_epublib.infolist():
        assert info.filename in RELATIVE_NAMELIST
    for file in RELATIVE_NAMELIST:
        if (DIRECTORY / file).is_dir():
            print("DIRECTORY", DIRECTORY / file)
            continue
        print(file)
        assert source_epublib.getinfo(file).file_size == (DIRECTORY / file).stat().st_size
        assert source_epublib.read(file) == (DIRECTORY / file).read_bytes()


def test_source(custom_source):
    with custom_source.open():
        assert set(custom_source.namelist()) == set(RELATIVE_NAMELIST)
        assert set(custom_source.file_namelist()) == set(RELATIVE_FILE_NAMELIST)
        assert custom_source.read_text("mimetype") == "application/epub+zip"
        assert custom_source.read_bytes("mimetype") == b"application/epub+zip"
        print()
        a = custom_source.infolist()
    for i in a:
        print(i)
        print(i.filename, i.is_dir())
