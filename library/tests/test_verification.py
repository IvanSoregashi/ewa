"""Tests for library.epub.verification EPUB verification classes.

Synthetic epub built inline (same pattern as plugins/epub test_recipe_package),
no repo fixtures. Sampling tests use uniformly valid/broken books so outcomes
are deterministic regardless of which chapters random.sample picks."""

import zipfile
from pathlib import Path

from library.epub.epub import EPUB
from library.epub.errors import EpubSkipReason
from library.epub.media_type import FileName
from library.epub.verification import HasNoGiantGifs, ValidXMLChapters

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


# ---------------------------------------------------------------------------
# ValidXMLChapters - spot check of one chapter (count=1)
# ---------------------------------------------------------------------------


def test_valid_xml_chapters_accepts_wellformed_xhtml(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})

    verification = ValidXMLChapters(count=1)
    assert verification.verify(EPUB(path)) is True
    assert verification.additional_info == ""
    assert verification.epub_info is not None


def test_valid_xml_chapters_rejects_broken_chapter(tmp_path: Path):
    """Exactly the artifact lxml's HTML serializer produces: <br> without the
    self-closing slash - well-formed HTML, invalid XML."""
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": BROKEN_CHAPTER})

    verification = ValidXMLChapters(count=1)
    assert verification.verify(EPUB(path)) is False
    assert verification.skip == EpubSkipReason.INVALID_XML_CHAPTERS
    assert verification.epub_info is not None
    assert "chapter.xhtml" in verification.additional_info


def test_valid_xml_chapters_rejects_empty_chapter(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": ""})

    verification = ValidXMLChapters(count=1)
    assert verification.verify(EPUB(path)) is False
    assert "chapter.xhtml" in verification.additional_info


def test_valid_xml_chapters_without_chapters_passes_vacuously(tmp_path: Path):
    """No chapters means nothing to sample, so there are no failures.
    (The old verify_chapters_xml(count=...) function raised ValueError here.)"""
    path = tmp_path / "book.epub"
    build_epub(path, {})

    verification = ValidXMLChapters(count=1)
    assert verification.verify(EPUB(path)) is True


# ---------------------------------------------------------------------------
# ValidXMLChapters - count-sampled or all chapters
# ---------------------------------------------------------------------------


def test_valid_xml_chapters_all_valid(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {f"OEBPS/text/ch{i}.xhtml": VALID_CHAPTER for i in range(3)})

    assert ValidXMLChapters().verify(EPUB(path)) is True  # default count covers all 3


def test_valid_xml_chapters_collects_all_failures(tmp_path: Path):
    """One broken chapter must not hide another: additional_info lists every
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

    verification = ValidXMLChapters()
    assert verification.verify(EPUB(path)) is False

    assert "2/3 of 3" in verification.additional_info
    assert "bad1.xhtml" in verification.additional_info
    assert "bad2.xhtml" in verification.additional_info
    assert "good.xhtml" not in verification.additional_info


def test_valid_xml_chapters_checks_sample_size(tmp_path: Path):
    """count=N verifies N random chapters; counts beyond the available
    chapters verify all."""
    path = tmp_path / "book.epub"
    build_epub(path, {f"OEBPS/text/bad{i}.xhtml": BROKEN_CHAPTER for i in range(3)})

    verification = ValidXMLChapters(count=2)
    assert verification.verify(EPUB(path)) is False
    assert "2/2 of 3" in verification.additional_info

    verification = ValidXMLChapters(count=10)  # count > available: all checked
    assert verification.verify(EPUB(path)) is False
    assert "3/3 of 3" in verification.additional_info


def test_valid_xml_chapters_ignores_non_chapter_resources(tmp_path: Path):
    """Chapter detection is by EPUB role; broken non-chapter entries must not
    fail the verification."""
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("OEBPS/text/not_a_chapter.txt", "<this is not xml at all")

    assert ValidXMLChapters().verify(EPUB(path)) is True


# ---------------------------------------------------------------------------
# HasNoGiantGifs
# ---------------------------------------------------------------------------


def test_has_no_giant_gifs_detects_oversized(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("OEBPS/images/big.gif", b"\x00" * (5 * 1024 * 1024 + 1))
        z.writestr("OEBPS/images/small.gif", b"\x00" * 1024)

    verification = HasNoGiantGifs()
    assert verification.verify(EPUB(path)) is False
    assert verification.skip == EpubSkipReason.BIG_GIFS
    assert verification.epub_info is not None
    assert "big.gif" in verification.additional_info
    assert "small.gif" not in verification.additional_info


def test_has_no_giant_gifs_passes_when_all_small(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("OEBPS/images/small.gif", b"\x00" * 1024)

    verification = HasNoGiantGifs()
    assert verification.verify(EPUB(path)) is True
    assert verification.additional_info == ""
