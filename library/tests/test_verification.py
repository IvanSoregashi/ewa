"""Tests for library.epub.verification chapter XML checks.

Synthetic epub built inline (same pattern as plugins/epub test_recipe_package),
no repo fixtures."""

import zipfile
from pathlib import Path

import pytest

from library.epub.epub import EPUB
from library.epub.media_type import FileName
from library.epub.resources import Resource
from library.epub.verification import verify_chapter_xml, verify_chapters_xml

VALID_CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><link rel="stylesheet" type="text/css" href="style.css"/></head>
  <body><p>Hello <br/> world</p><img src="pic.png" alt="x"/></body>
</html>"""

BROKEN_CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><link rel="stylesheet" type="text/css" href="style.css"></head>
  <body><p>Hello <br> world</p></body>
</html>"""


def build_epub(path: Path, chapters: dict[str, str]) -> None:
    manifest_items = "\n".join(
        f'<item id="ch{i}" href="{name.removeprefix("OEBPS/")}" media-type="application/xhtml+xml"/>'
        for i, name in enumerate(chapters)
    )
    spine_items = "\n".join(f'<itemref idref="ch{i}"/>' for i in range(len(chapters)))
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>t</dc:title><dc:identifier id="id">x</dc:identifier><dc:language>en</dc:language></metadata>
 <manifest>{manifest_items}
 </manifest>
 <spine>{spine_items}
 </spine>
</package>"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(FileName.MIMETYPE, "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        for name, content in chapters.items():
            z.writestr(name, content)


def make_resource(markup: str, filename: str = "OEBPS/text/chapter.xhtml") -> Resource:
    from io import BytesIO
    from zipfile import ZipInfo

    data = markup.encode("utf-8")
    info = ZipInfo(filename)
    info.file_size = len(data)
    return Resource(info=info, stream_bytes=lambda i: BytesIO(data))


# ---------------------------------------------------------------------------
# verify_chapter_xml
# ---------------------------------------------------------------------------


def test_verify_chapter_xml_accepts_wellformed_xhtml():
    assert verify_chapter_xml(make_resource(VALID_CHAPTER)) is True


def test_verify_chapter_xml_rejects_unclosed_void_element():
    """Exactly the artifact lxml's HTML serializer produces: <br> without the
    self-closing slash - well-formed HTML, invalid XML."""
    with pytest.raises(ValueError, match="chapter.xhtml.*not well-formed XML"):
        verify_chapter_xml(make_resource(BROKEN_CHAPTER))


def test_verify_chapter_xml_rejects_empty_content():
    with pytest.raises(ValueError, match="not well-formed XML"):
        verify_chapter_xml(make_resource(""))


# ---------------------------------------------------------------------------
# verify_chapters_xml
# ---------------------------------------------------------------------------


def test_verify_chapters_xml_all_valid(tmp_path: Path):
    path = tmp_path / "book.epub"
    chapters = {f"OEBPS/text/ch{i}.xhtml": VALID_CHAPTER for i in range(3)}
    build_epub(path, chapters)

    assert verify_chapters_xml(EPUB(path)) is True


def test_verify_chapters_xml_collects_all_failures(tmp_path: Path):
    """One broken chapter must not hide another: the error lists every
    offending filename."""
    path = tmp_path / "book.epub"
    build_epub(
        path,
        {
            "OEBPS/text/good.xhtml": VALID_CHAPTER,
            "OEBPS/text/bad1.xhtml": BROKEN_CHAPTER,
            "OEBPS/text/bad2.xhtml": BROKEN_CHAPTER,
        },
    )

    with pytest.raises(ValueError) as excinfo:
        verify_chapters_xml(EPUB(path))

    message = str(excinfo.value)
    assert "2 chapter(s)" in message
    assert "bad1.xhtml" in message
    assert "bad2.xhtml" in message
    assert "good.xhtml" not in message


def test_verify_chapters_xml_ignores_non_chapter_resources(tmp_path: Path):
    """Opf/container are XML too, but the check targets chapters only; a
    broken non-HTML resource must not fail the verification."""
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("OEBPS/text/not_a_chapter.txt", "<this is not xml at all")

    assert verify_chapters_xml(EPUB(path)) is True
