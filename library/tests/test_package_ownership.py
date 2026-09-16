import io
from zipfile import ZipFile

import pytest

from library.epub.epub import EPUB
from library.epub.resources import Resource, ResourceIndex, ResourceSelection
from library.epub.xml_models.package_metadata import Meta
from library.epub.xml_models.package_sequences import Guide
from .test_package import make_epub, relocation_state


def test_add_resource_updates_archive_and_manifest_on_export(tmp_path):
    epub = make_epub(tmp_path)
    image = Resource.from_bytes("OEBPS/images/new cover.jpg", b"image")
    item = epub.package.add_resource(image, item_id="cover", properties="cover-image")
    assert item.href == "images/new%20cover.jpg"
    assert epub.package.document.manifest.find_item(id="cover") is item
    assert epub.resources.by_path(image.filename) is image
    output = tmp_path / "added.epub"
    epub.package_into(output)
    reopened = EPUB(output).package
    assert reopened.document.manifest.find_item(id="cover").properties == "cover-image"
    assert reopened.resource_for_href(item.href).content == b"image"


def test_duplicate_ids_paths_and_foreign_ownership_rejected_without_changes(tmp_path):
    epub = make_epub(tmp_path)
    package = epub.package
    original = relocation_state(epub)
    for resource, item_id in [
        (Resource.from_bytes("new.png", b"x"), "chapter"),
        (Resource.from_bytes("OEBPS/text/chapter.xhtml", b"x"), "other"),
    ]:
        with pytest.raises(ValueError):
            package.add_resource(resource, item_id=item_id)
        assert relocation_state(epub) == original
    with pytest.raises(ValueError, match="not owned"):
        package.remove_resource(Resource.from_bytes("OEBPS/text/chapter.xhtml", b"x"))
    assert relocation_state(epub) == original


def test_declare_existing_resource_without_duplicating_inventory(tmp_path):
    epub = make_epub(tmp_path)
    image = Resource.from_bytes("new.png", b"x")
    epub.resources.add(image)
    size = len(epub.resources)
    epub.package.add_resource(image, item_id="new")
    assert len(epub.resources) == size
    with pytest.raises(ValueError, match="already declared"):
        epub.package.add_resource(image, item_id="another")
    assert len(epub.package.document.manifest.items) == 2


def test_remove_rejects_opf_references_then_cleans_them_explicitly(tmp_path):
    epub = make_epub(tmp_path)
    package = epub.package
    chapter = epub.resources.by_path("OEBPS/text/chapter.xhtml")
    image = Resource.from_bytes("OEBPS/image.png", b"x")
    remaining = package.add_resource(image, item_id="image")
    remaining.fallback = "chapter"
    remaining.overlay = "chapter"
    package.document.guide = Guide()
    package.document.guide.add_reference(type="text", href="text/chapter.xhtml#start")
    package.document.spine.toc = "chapter"
    package.document.metadata.metas.extend(
        [
            Meta(name="cover", content="chapter"),
            Meta(id="r1", property="title-type", refines="#chapter", text="main"),
            Meta(property="alternate-script", refines="#r1", text="other"),
        ]
    )
    before = relocation_state(epub)
    with pytest.raises(ValueError, match="OPF references"):
        package.remove_resource(chapter)
    assert relocation_state(epub) == before
    package.remove_resource(chapter, remove_references=True)
    assert package.document.manifest.find_item(id="chapter") is None
    assert epub.resources.by_path(chapter.filename) is None
    assert package.document.spine.itemrefs == []
    assert package.document.spine.toc is None
    assert package.document.guide.references == []
    assert package.document.metadata.metas == []
    assert remaining.fallback is remaining.overlay is None
    # The removal has no permanent flag: the same resource can be re-added.
    package.add_resource(chapter, item_id="chapter-again")
    package.document.spine.add_itemref("chapter-again")
    output = tmp_path / "readded.epub"
    epub.package_into(output)
    reopened = EPUB(output).package
    assert reopened.document.manifest.find_item(id="chapter-again") is not None
    assert reopened.resource_for_href("text/chapter.xhtml").content == b"<html/>"


def test_plain_remove_is_reflected_in_export(tmp_path):
    epub = make_epub(tmp_path)
    resource = Resource.from_bytes("unused.png", b"x")
    epub.package.add_resource(resource, item_id="unused")
    epub.package.remove_resource(resource)
    output = io.BytesIO()
    epub.package_into(output)
    with ZipFile(output) as archive:
        assert "unused.png" not in archive.namelist()
        assert "META-INF/container.xml" in archive.namelist()
        assert "OEBPS/book.opf" in archive.namelist() or "OEBPS/content.opf" in archive.namelist()
        assert b'id="unused"' not in archive.read("OEBPS/content.opf")


def test_selection_has_no_membership_mutators_and_tracks_resource_edits():
    resource = Resource.from_bytes("old.png", b"x")
    index = ResourceIndex.from_resource_list([resource])
    selection = index.by_media_type(resource.media_type)
    assert type(selection) is ResourceSelection
    for method in ("add", "remove", "rename"):
        assert not hasattr(selection, method)
    index.rename(resource, "new.png")
    assert selection.by_path("new.png") is resource
    index.remove(resource)
    assert len(index) == 0
    assert tuple(selection) == (resource,)  # documented membership snapshot
    index.add(resource)
    with pytest.raises(ValueError):
        index.add(resource)
    assert len(index) == 1


def test_package_lookups_reflect_direct_xml_edits(tmp_path):
    package = make_epub(tmp_path).package
    item = package.document.manifest.find_item(id="chapter")
    item.id = "renamed"
    item.href = "other.xhtml"
    assert package.document.manifest.find_item(id="chapter") is None
    assert package.document.manifest.find_item(id="renamed") is item
    assert package.manifest_item_by_path("OEBPS/text/chapter.xhtml") is None
    assert package.manifest_item_by_path("OEBPS/other.xhtml") is item
