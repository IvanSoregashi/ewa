"""End-to-end smoke for the recipe_package fixes: opf relocation, manifest
removal, rename handling, and packaging - using a synthetic epub, no repo fixtures."""

import zipfile
from pathlib import Path

import pytest

from epub.errors import EpubSkipReason, InvalidEpubOutput
from epub.processing import ProcessingContext
from epub.recipe_package import (
    DeclareMissingResources,
    PackageEpub,
    relocate_package,
    replace_links,
    validate_epub_output,
)
from epub.verification import AllResourcesInManifest, NoUnmatchedLinks
from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import FileName
from library.epub.resources import Resource


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


def test_relocate_remove_font_sync_package(tmp_path: Path):
    src = tmp_path / "book.epub"
    build_epub(src)

    epub = EPUB(src)
    assert relocate_package(epub) is True  # opf relocated

    # font removal: manifest item first (manifest needs the resource to build),
    # then the resource itself; the package document is synced into the opf resource
    fonts = epub.resources.by_path("OEBPS/fonts/SerenePanda.ttf")
    assert fonts is not None
    epub.package.remove_resource(fonts)

    out = tmp_path / "out.epub"
    epub.package_into(out)

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names[0] == "mimetype"
        assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert "OEBPS/fonts/SerenePanda.ttf" not in names  # resource removed
        assert "OEBPS/content.opf" not in names
        assert "content.opf" in names  # opf relocated to the root

        container = z.read("META-INF/container.xml").decode()
        assert 'full-path="content.opf"' in container  # container updated for the new opf location

        opf = z.read("content.opf").decode()
        assert 'href="fonts/SerenePanda.ttf"' not in opf  # font manifest item removed
        assert 'href="OEBPS/text/chapter.xhtml"' in opf  # hrefs rewritten for the new opf location
        assert 'href="OEBPS/images/pic.png"' in opf  # untouched image keeps its archive-path href


def test_replace_links_updates_href_and_media_type(tmp_path: Path):
    """Simulate what perform_image_optimization does on png->jpg: rename the
    resource, then update the manifest through replace_links."""
    src = tmp_path / "book.epub"
    build_epub(src)
    epub = EPUB(src)
    relocate_package(epub)

    image = epub.resources.by_path("OEBPS/images/pic.png")
    assert image is not None
    epub.resources.rename(image, "OEBPS/images/pic.jpg")
    assert image.media_type == "image/jpeg"

    replace_links(epub, {"OEBPS/images/pic.png": "OEBPS/images/pic.jpg"})
    epub.package.flush()

    opf = epub.package.resource.content.decode()
    assert 'href="OEBPS/images/pic.jpg"' in opf
    assert 'media-type="image/jpeg"' in opf
    assert 'href="OEBPS/images/pic.png"' not in opf
    assert 'media-type="image/png"' not in opf


def test_relocate_is_noop_for_root_opf(tmp_path: Path):
    src = tmp_path / "already.epub"
    build_epub(src)
    epub = EPUB(src)
    assert relocate_package(epub) is True

    # second call: opf is now at the root
    assert relocate_package(epub) is False
    assert epub.package.resource.info.filename == FileName.DEFAULT_OPF


def test_package_operation_writes_verified_output(tmp_path: Path):
    source = tmp_path / "book.epub"
    destination = tmp_path / "output.epub"
    build_epub(source)
    original_bytes = source.read_bytes()

    with ProcessingContext() as context:
        context.open_epub(source).perform(PackageEpub(destination))
        assert context.result is None

    assert context.result is not None
    assert context.result.success
    assert context.result.error is None
    assert context.result.new_epub == validate_epub_output(destination)
    assert source.read_bytes() == original_bytes
    with zipfile.ZipFile(destination) as archive:
        assert archive.namelist()[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED


@pytest.mark.parametrize("missing", [False, True])
def test_output_validation_preserves_cause(tmp_path: Path, missing: bool):
    output = tmp_path / "invalid.epub"
    if not missing:
        output.write_bytes(b"not an archive")

    with pytest.raises(InvalidEpubOutput) as failure:
        validate_epub_output(output)

    cause = failure.value.__cause__
    assert isinstance(cause, FileNotFoundError if missing else ValueError)
    assert str(failure.value) == str(cause)


@pytest.mark.parametrize("relocate", [False, True])
def test_declare_missing_resources_preserves_existing_manifest_and_inventory(tmp_path: Path, relocate: bool):
    source = tmp_path / "book.epub"
    destination = tmp_path / "output.epub"
    build_epub(source)
    missing_paths = ["OEBPS/images/new cover.png", "toc.ncx", "nav.xhtml", "data.xml", "script.js", "extra.bin"]
    with ProcessingContext() as context:
        context.open_epub(source)
        epub = context.epub
        package = epub.package
        # Existing declarations may use encoded paths and IDs outside the manifest.
        package.document.id = "resource-1"
        image_item = package.document.manifest.find_item(id="img")
        assert image_item is not None
        image_item.href = "images/%70ic.png"
        image_item.properties = "cover-image"
        if relocate:
            relocate_package(epub)
        for path in [*missing_paths, "META-INF/encryption.xml", "META-INF/vendor.bin"]:
            epub.resources.add(Resource.from_bytes(path, b"test"))
        inventory = list(epub.resources)
        manifest_before = package.document.manifest.model_dump()
        check = AllResourcesInManifest()

        assert [resource.filename for resource in package.undeclared_resources] == missing_paths
        failure = check.verify(context)
        assert failure is not None and all(path in failure for path in missing_paths)
        assert package.document.manifest.model_dump() == manifest_before
        assert context.unmatched_links == {}
        assert NoUnmatchedLinks().verify(context) is None

        context.perform(DeclareMissingResources()).verify(check)
        assert list(epub.resources) == inventory
        assert package.document.manifest.model_dump()["items"][:3] == manifest_before["items"]
        added = package.document.manifest.items[3:]
        assert [item.id for item in added] == [f"resource-{i}" for i in range(2, 8)]
        assert [require(package.resource_for_href(item.href)).filename for item in added] == missing_paths
        assert "%20" in added[0].href
        assert added[0].media_type == "image/png"
        manifest_after = package.document.manifest.model_dump()
        context.perform(DeclareMissingResources())
        assert package.document.manifest.model_dump() == manifest_after
        context.perform(PackageEpub(destination))

    assert context.result is not None and context.result.success
    reopened = EPUB(destination).package
    assert not reopened.undeclared_resources
    assert reopened.document.manifest.model_dump() == manifest_after


def test_manifest_check_skips_without_repairing_or_reporting_unmatched_html(tmp_path: Path):
    source = tmp_path / "book.epub"
    build_epub(source)
    with ProcessingContext() as context:
        context.open_epub(source)
        context.epub.package.document.manifest.remove_item(_id="img")
        context.verify(AllResourcesInManifest())
        pytest.fail("Missing manifest entry must stop processing")

    assert context.result is not None
    assert context.result.skip == EpubSkipReason.UNDECLARED_RESOURCES
    assert context.result.error is None
    assert context.epub.package.manifest_item_by_path("OEBPS/images/pic.png") is None
    assert context.unmatched_links == {}
