import zipfile
from pathlib import Path
from library.epub.epub import EPUB
from library.epub.media_type import FileName
from epub.errors import EpubSkipReason
from epub.verification import HasNoGiantGifs, OPFPath, SerenePanda
from epub.protocols import VerificationResult
from library.epub.resources import Resource

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


def test_has_no_giant_gifs_detects_oversized(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("OEBPS/images/big.gif", b"\x00" * (5 * 1024 * 1024 + 1))
        z.writestr("OEBPS/images/small.gif", b"\x00" * 1024)

    verification = HasNoGiantGifs()
    result = verification.verify(EPUB(path))
    assert result.passed is False
    assert "big.gif" in result.details
    assert "small.gif" not in result.details


def test_has_no_giant_gifs_passes_when_all_small(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("OEBPS/images/small.gif", b"\x00" * 1024)

    verification = HasNoGiantGifs()
    result = verification.verify(EPUB(path))
    assert result.passed is True
    assert result.details == ""


def test_configured_checks_chain_and_short_circuit(tmp_path):
    path = tmp_path / "book.epub"
    build_epub(path, {})
    epub = EPUB(path)
    reached = []

    class Sentinel:
        def verify(self, epub):
            reached.append(True)
            return VerificationResult(True)

    for check in (OPFPath("OEBPS/content.opf"), SerenePanda(), Sentinel()):
        result = check.verify(epub)
        if not result.passed:
            break
    assert isinstance(check, SerenePanda)
    assert check.skip_reason == EpubSkipReason.SERENE_PANDA_FONT
    assert "font not found" in result.details
    assert reached == []
    assert not OPFPath().verify(epub).passed


def test_font_check_modes_and_reuse(tmp_path):
    path = tmp_path / "book.epub"
    build_epub(path, {})
    epub = EPUB(path)
    check = SerenePanda(strict=True)
    assert not check.verify(epub).passed
    epub.resources.add(Resource.from_bytes(FileName.SP_FONT, b"font"))
    assert check.verify(epub).passed
    epub.resources.add(Resource.from_bytes("other.ttf", b"font"))
    assert not check.verify(epub).passed
    assert not SerenePanda().verify(epub).passed


def test_default_skip_reasons_can_be_overridden_per_instance():
    assert OPFPath().skip_reason == EpubSkipReason.NON_DEFAULT_OPF
    assert HasNoGiantGifs().skip_reason == EpubSkipReason.BIG_GIFS
    check = SerenePanda()
    check.skip_reason = EpubSkipReason.NOT_IMPLEMENTED
    assert check.skip_reason == EpubSkipReason.NOT_IMPLEMENTED
    assert SerenePanda().skip_reason == EpubSkipReason.SERENE_PANDA_FONT
