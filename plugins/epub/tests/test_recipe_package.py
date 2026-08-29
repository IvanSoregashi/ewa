"""End-to-end smoke for the recipe_package fixes: opf standardization, manifest
removal, sync, and packaging - using a synthetic epub, no repo fixtures."""

import zipfile
from io import BytesIO
from pathlib import Path

from epub.recipe_package import relocate_package
from library.epub.epub import EPUB
from library.epub.media_type import FileName


def build_epub(path: Path) -> None:
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>t</dc:title><dc:identifier id="id">x</dc:identifier><dc:language>en</dc:language></metadata>
 <manifest>
  <item id="font" href="fonts/SerenePanda.ttf" media-type="font/ttf"/>
  <item id="ch" href="text/chapter.xhtml" media-type="application/xhtml+xml"/>
  <item id="img" href="images/pic.png" media-type="image/png"/>
 </manifest>
 <spine><itemref idref="ch"/></spine>
</package>"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/fonts/SerenePanda.ttf", b"fakettf")
        z.writestr("OEBPS/text/chapter.xhtml", '<html><body><img src="../images/pic.png"/></body></html>')
        z.writestr("OEBPS/images/pic.png", b"fakepng" * 1000)


def test_standardize_remove_font_sync_package(tmp_path: Path):
    src = tmp_path / "book.epub"
    build_epub(src)

    epub = EPUB(src)
    assert relocate_package(epub) is True  # opf relocated

    # font removal: manifest item first (manifest needs the resource to build),
    # then the resource itself; the package document is synced into the opf resource
    fonts = epub.resources.by_path("OEBPS/fonts/SerenePanda.ttf")
    epub.core.manifest.remove_by_path("OEBPS/fonts/SerenePanda.ttf")
    epub.resources.remove(fonts)
    epub.core.package.manifest.remove_item(path="OEBPS/fonts/SerenePanda.ttf")
    epub.core.package_resource.content = epub.core.package.to_xml_bytes()

    out = tmp_path / "out.epub"
    epub.package_into(out)

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names[0] == "mimetype"
        assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert "fonts/SerenePanda.ttf" not in names  # resource removed
        assert "OEBPS/content.opf" not in names
        assert "content.opf" in names  # opf relocated to the root

        container = z.read("META-INF/container.xml").decode()
        assert 'full-path="content.opf"' in container  # container regenerated for the new opf location

        opf = z.read("content.opf").decode()
        assert 'href="fonts/SerenePanda.ttf"' not in opf  # font manifest item removed
        assert 'href="OEBPS/text/chapter.xhtml"' in opf  # hrefs rewritten for the new opf location
        assert 'href="OEBPS/images/pic.png"' in opf


def test_standardize_is_noop_for_root_opf(tmp_path: Path):
    src = tmp_path / "already.epub"
    build_epub(src)
    epub = EPUB(src)
    assert relocate_package(epub) is True

    # second call: opf is now at the root
    assert relocate_package(epub) is False
    assert epub.core.package_resource.info.filename == FileName.DEFAULT_OPF
