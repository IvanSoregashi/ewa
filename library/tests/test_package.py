import io
from zipfile import ZipFile

import pytest

from library.epub.epub import EPUB


OPF = b"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>Original</dc:title>
    </metadata>
    <manifest><item id="chapter" href="text/chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
    <spine><itemref idref="chapter"/></spine>
</package>"""


def make_epub(tmp_path, *, package_bytes=OPF, container_path="OEBPS/content.opf", extra_opf=False):
    path = tmp_path / "input.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            f'''<container
          xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
          <rootfiles><rootfile full-path="{container_path}" media-type="application/oebps-package+xml"/></rootfiles>
        </container>''',
        )
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
    assert epub.package.flush()  # Only the discovered container has been parsed.
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


def test_discovery_retains_container_and_relocation_survives_export(tmp_path):
    from library.epub.package import EpubPackage
    from library.epub.xml_models.package_sequences import Guide

    epub = make_epub(tmp_path)
    package = epub.package
    assert EpubPackage.from_resources(epub.resources).resource is package.resource
    assert package.container_resource is epub.resources.by_path("META-INF/container.xml")
    assert package.container.opf_path == "OEBPS/content.opf"
    package.document.guide = Guide()
    package.document.guide.add_reference(type="text", href="text/chapter.xhtml#start")
    old_manifest = epub.core.manifest
    assert package.relocate("package/book.opf")
    assert epub.resources.by_path("OEBPS/content.opf") is None
    assert epub.resources.by_path("package/book.opf") is package.resource
    assert package.container.opf_path == "package/book.opf"
    assert package.document.guide.references[0].href == "../OEBPS/text/chapter.xhtml#start"
    assert epub.core.manifest is not old_manifest
    assert epub.core.manifest.by_path("../OEBPS/text/chapter.xhtml") is not None
    assert not package.relocate("package/book.opf")
    output = tmp_path / "relocated.epub"
    epub.package_into(output)
    reopened = EPUB(output).package
    assert reopened.resource.filename == "package/book.opf"
    assert reopened.resource_for_href(reopened.document.manifest.items[0].href).content == b"<html/>"


def test_relocation_collision_preserves_documents(tmp_path):
    epub = make_epub(tmp_path, extra_opf=True)
    package = epub.package
    before = package.document.to_xml_bytes(), package.container.to_xml_bytes()
    with pytest.raises(ValueError, match="already exists"):
        package.relocate("unused.opf")
    assert package.resource.filename == "OEBPS/content.opf"
    assert (package.document.to_xml_bytes(), package.container.to_xml_bytes()) == before
    assert epub.resources.by_path("OEBPS/content.opf") is package.resource


@pytest.mark.parametrize("relocate", [False, True])
def test_missing_container_created_and_exported(tmp_path, relocate):
    from library.epub.package import EpubPackage

    path = tmp_path / "without-container.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip")
        archive.writestr("OEBPS/book.opf", OPF)
        archive.writestr("OEBPS/text/chapter.xhtml", b"<html/>")
    epub = EPUB(path)
    package = epub.package
    container_resource = epub.resources.by_path("META-INF/container.xml")
    assert package.container_resource is container_resource
    assert package.container.opf_path == "OEBPS/book.opf"
    assert EpubPackage.from_resources(epub.resources).container_resource is container_resource
    assert len(epub.resources) == 4
    if relocate:
        assert package.relocate("book.opf")
    output = tmp_path / "repaired.epub"
    epub.package_into(output)
    reopened = EPUB(output).package
    assert reopened.container.opf_path == package.resource.filename
    assert reopened.resource_for_href(reopened.document.manifest.items[0].href).content == b"<html/>"
    with ZipFile(output) as archive:
        assert archive.namelist().count("META-INF/container.xml") == 1
    assert "META-INF/container.xml" not in epub.source.namelist()


@pytest.mark.parametrize("opf_count", [0, 2])
def test_missing_container_not_created_without_unique_opf(opf_count):
    from library.epub.package import EpubPackage
    from library.epub.resources import Resource, ResourceIndex

    resources = ResourceIndex.from_resource_list([Resource.from_bytes(f"book{i}.opf", OPF) for i in range(opf_count)])
    with pytest.raises(ValueError, match="unique OPF"):
        EpubPackage.from_resources(resources)
    assert len(resources) == opf_count
    assert resources.by_path("META-INF/container.xml") is None


@pytest.mark.parametrize(
    "href", ["https://example.com/audio.mp3", "//example.com/audio.mp3", "data:audio/mpeg;base64,AA=="]
)
def test_relocation_leaves_remote_hrefs_unchanged(tmp_path, href):
    package = make_epub(tmp_path).package
    remote = package.document.manifest.add_item(id="remote", href=href, media_type="audio/mpeg")
    package.relocate("book.opf")
    assert remote.href == href


def test_repeated_relocation_keeps_targets_and_content(tmp_path):
    from library.epub.xml_models.package_sequences import Guide

    epub = make_epub(tmp_path)
    package = epub.package
    chapter = epub.resources.by_path("OEBPS/text/chapter.xhtml")
    package.document.guide = Guide()
    package.document.guide.add_reference(type="text", href="text/chapter.xhtml#start")
    item = package.document.manifest.items[0]
    guide = package.document.guide.references[0]
    original_paths = set(epub.source.namelist())

    for new_path, expected_href in [
        ("content.opf", "OEBPS/text/chapter.xhtml"),
        ("deep/package/book.opf", "../../OEBPS/text/chapter.xhtml"),
        ("OEBPS/content.opf", "text/chapter.xhtml"),
    ]:
        old_path = package.resource.filename
        assert package.relocate(new_path)
        assert epub.resources.by_path(old_path) is None
        assert epub.resources.by_path(new_path) is package.resource
        assert item.href == expected_href
        assert guide.href == expected_href + "#start"
        assert package.resource_for_href(item.href) is chapter
        assert package.container.opf_path == new_path

        output = tmp_path / (new_path.replace("/", "_") + ".epub")
        epub.package_into(output)
        reopened = EPUB(output).package
        assert reopened.resource.filename == new_path
        assert reopened.document.guide.references[0].href == guide.href
        assert reopened.document.spine.itemrefs[0].idref == "chapter"
        assert reopened.document.metadata.title == "Original"
        with ZipFile(output) as archive:
            expected_paths = (original_paths - {"OEBPS/content.opf"}) | {new_path}
            assert len(archive.namelist()) == len(expected_paths)
            assert set(archive.namelist()) == expected_paths
            assert archive.read("OEBPS/text/chapter.xhtml") == b"<html/>"


def relocation_state(epub):
    package = epub.package
    return (
        package.resource.filename,
        package.document.to_xml_bytes(),
        package.container.to_xml_bytes(),
        package.resource.content,
        package.container_resource.content,
        [(resource.filename, epub.resources.by_path(resource.filename)) for resource in epub.resources],
    )


@pytest.mark.parametrize("document_name", ["document", "container"])
def test_failed_relocation_serialization_leaves_state_unchanged(tmp_path, monkeypatch, document_name):
    epub = make_epub(tmp_path)
    before = relocation_state(epub)

    def fail_serialization(*args, **kwargs):
        raise RuntimeError("serialization failed")

    with monkeypatch.context() as patch:
        patch.setattr(type(getattr(epub.package, document_name)), "to_xml_bytes", fail_serialization)
        with pytest.raises(RuntimeError, match="serialization failed"):
            epub.package.relocate("moved.opf")
    assert relocation_state(epub) == before
    assert epub.resources.by_path("moved.opf") is None


def test_relocation_rejects_mismatched_container_without_changes(tmp_path):
    epub = make_epub(tmp_path)
    epub.package.container.rootfiles[0].full_path = "different.opf"
    before = relocation_state(epub)
    with pytest.raises(ValueError, match="does not reference"):
        epub.package.relocate("moved.opf")
    assert relocation_state(epub) == before
    assert epub.resources.by_path("moved.opf") is None
