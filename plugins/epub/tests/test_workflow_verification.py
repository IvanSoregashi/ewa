import zipfile
from pathlib import Path
from epub.processing import ProcessingContext
from library.epub.media_type import FileName
from epub.errors import EpubSkipReason
from epub.verification import HasNoGiantGifs, OPFPath, SerenePanda
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
    with ProcessingContext() as context:
        context.open_epub(path)
        result = verification.verify(context)
    assert result is not None
    assert "big.gif" in result
    assert "small.gif" not in result


def test_has_no_giant_gifs_passes_when_all_small(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, {"OEBPS/text/chapter.xhtml": VALID_CHAPTER})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("OEBPS/images/small.gif", b"\x00" * 1024)

    verification = HasNoGiantGifs()
    with ProcessingContext() as context:
        context.open_epub(path)
        result = verification.verify(context)
    assert result is None


def test_configured_checks_chain_and_short_circuit(tmp_path):
    path = tmp_path / "book.epub"
    build_epub(path, {})
    reached = []

    class Sentinel:
        skip_reason = EpubSkipReason.NOT_IMPLEMENTED

        def verify(self, context):
            reached.append(True)
            return None

    with ProcessingContext() as context:
        context.open_epub(path)
        wrong_path = OPFPath().verify(context)
        for check in (OPFPath("OEBPS/content.opf"), SerenePanda(), Sentinel()):
            context.verify(check)
    assert context.result is not None
    assert context.result.skip == EpubSkipReason.SERENE_PANDA_FONT
    assert "font not found" in context.result.details
    assert reached == []
    assert wrong_path is not None


def test_font_check_modes_and_reuse(tmp_path):
    path = tmp_path / "book.epub"
    build_epub(path, {})
    check = SerenePanda(strict=True)
    with ProcessingContext() as context:
        context.open_epub(path)
        missing = check.verify(context)
        context.epub.resources.add(Resource.from_bytes(FileName.SP_FONT, b"font"))
        matching = check.verify(context)
        context.epub.resources.add(Resource.from_bytes("other.ttf", b"font"))
        extra = check.verify(context)
        relaxed = SerenePanda().verify(context)
    assert missing is not None
    assert matching is None
    assert extra is not None
    assert relaxed is not None


def test_default_skip_reasons_can_be_overridden_per_instance():
    assert OPFPath().skip_reason == EpubSkipReason.NON_DEFAULT_OPF
    assert HasNoGiantGifs().skip_reason == EpubSkipReason.BIG_GIFS
    check = SerenePanda()
    check.skip_reason = EpubSkipReason.NOT_IMPLEMENTED
    assert check.skip_reason == EpubSkipReason.NOT_IMPLEMENTED
    assert SerenePanda().skip_reason == EpubSkipReason.SERENE_PANDA_FONT
