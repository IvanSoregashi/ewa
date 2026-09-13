import io
from zipfile import ZipFile

import pytest

from library.epub.epub import EPUB


OPF = b'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>Original</dc:title>
    </metadata>
    <manifest><item id="chapter" href="text/chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
    <spine><itemref idref="chapter"/></spine>
</package>'''


def make_epub(tmp_path, *, package_bytes=OPF, container_path="OEBPS/content.opf", extra_opf=False):
    path = tmp_path / "input.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip")
        archive.writestr("META-INF/container.xml", f'''<container
          xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
          <rootfiles><rootfile full-path="{container_path}" media-type="application/oebps-package+xml"/></rootfiles>
        </container>''')
        archive.writestr("OEBPS/content.opf", package_bytes)
        archive.writestr("OEBPS/text/chapter.xhtml", b"<html/>")
        if extra_opf:
            archive.writestr("unused.opf", b"not the selected package")
    return EPUB(path)


def test_document_edits_survive_export_without_manual_serialization(tmp_path):
    epub = make_epub(tmp_path)
    package = epub.package
    package.document.metadata.titles[0].text = "Edited"
    output = tmp_path / "output.epub"
    epub.package_into(output)
    assert EPUB(output).package.document.metadata.title == "Edited"
    assert package.flush()


@pytest.mark.parametrize("inspect_document", [False, True])
def test_export_serializes_loaded_document_only(tmp_path, inspect_document):
    epub = make_epub(tmp_path)
    if inspect_document:
        assert epub.package.document.metadata.title == "Original"
    output = io.BytesIO()
    epub.package_into(output)
    with ZipFile(output) as archive:
        exported = archive.read("OEBPS/content.opf")
        if inspect_document:
            from library.epub.xml_models.package_document import PackageDocument

            document = PackageDocument.from_xml_bytes(exported)
            assert document.metadata.title == "Original"
            assert document.manifest.items[0].href == "text/chapter.xhtml"
            assert document.spine.itemrefs[0].idref == "chapter"
        else:
            assert exported == OPF


def test_package_binding_and_flush_do_not_parse_unopened_document(tmp_path):
    epub = make_epub(tmp_path, package_bytes=b"unparseable OPF")
    assert epub.package.resource.filename == "OEBPS/content.opf"
    assert not epub.package.flush()
    output = io.BytesIO()
    epub.package_into(output)
    with ZipFile(output) as archive:
        assert archive.read("OEBPS/content.opf") == b"unparseable OPF"


def test_container_selects_package_among_multiple_opfs(tmp_path):
    epub = make_epub(tmp_path, extra_opf=True)
    assert epub.package.document.metadata.title == "Original"
    assert epub.core.package is epub.package.document
    assert epub.core.package_resource is epub.package.resource


def test_existing_container_is_not_overridden_by_filename_guess(tmp_path):
    epub = make_epub(tmp_path, container_path="missing.opf")
    with pytest.raises(ValueError, match="missing.opf"):
        _ = epub.package


def test_package_resolves_resources_and_missing_entries(tmp_path):
    epub = make_epub(tmp_path)
    package = epub.package
    assert package.resource_for_href("text/chapter.xhtml") is epub.resources.by_path("OEBPS/text/chapter.xhtml")
    assert package.resource_for_href("missing.xhtml") is None
    assert package.relative_href("OEBPS/text/chapter.xhtml#part") == "text/chapter.xhtml#part"
    assert package.resolve_href("../images/pic.jpg") == "images/pic.jpg"


def test_resolution_uses_current_resource_location(tmp_path):
    epub = make_epub(tmp_path)
    package = epub.package
    # Href rewriting is the relocating operation's responsibility. Resolution
    # itself must use the current resource location, not an old copied path.
    package.resource.filename = "content.opf"
    assert package.resolve_href("text/chapter.xhtml") == "text/chapter.xhtml"
