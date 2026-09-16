import pytest

from library.epub.xml_models.package_sequences import Manifest
from library.epub.resources import Resource, ResourceIndex
from .test_package import make_epub, relocation_state


def test_find_matches_all_attributes_and_tracks_edits():
    manifest = Manifest()
    first = manifest.add_item("a", "./a.xhtml", "text/html", properties="nav scripted")
    manifest.add_item("b", "b.xhtml", "text/html")
    assert manifest.find_item(media_type="text/html") is first
    assert manifest.find_item(id="a", href="./a.xhtml", properties="nav scripted") is first
    assert manifest.find_item(id="a", href="b.xhtml") is None
    assert manifest.find_item(href="a.xhtml") is None
    assert manifest.find_item(properties="nav") is None
    first.id = "changed"
    assert manifest.find_item(id="a") is None
    assert manifest.find_item(id="changed") is first
    with pytest.raises(ValueError):
        manifest.find_item()


@pytest.mark.parametrize(
    "values",
    [
        ("a", "b.xhtml", "text/html"),
        ("b", "a.xhtml", "text/html"),
        ("", "b.xhtml", "text/html"),
        ("bad id", "b.xhtml", "text/html"),
        ("b", " ", "text/html"),
        ("b", "b.xhtml", ""),
    ],
)
def test_invalid_addition_leaves_manifest_unchanged(values):
    manifest = Manifest()
    original = manifest.add_item("a", "a.xhtml", "text/html")
    with pytest.raises(ValueError):
        manifest.add_item(*values)
    assert len(manifest.items) == 1
    assert manifest.items[0] is original


def test_declarations_roundtrip_and_existing_removal_api():
    manifest = Manifest()
    manifest.add_item("a", "a.xhtml", "text/html", fallback="b", overlay="audio")
    parsed = Manifest.from_xml(manifest.to_xml())
    item = parsed.find_item(fallback="b", overlay="audio")
    assert item.id == "a"
    parsed.remove_item(item=item)
    assert parsed.items == []
    manifest.remove_item(path="a.xhtml")
    assert not manifest.has_path("a.xhtml")


def test_package_checks_other_sections_and_resolved_targets(tmp_path):
    epub = make_epub(tmp_path)
    package = epub.package
    package.document.id = "package-id"
    chapter = package.document.manifest.find_item(id="chapter")
    chapter.href = "./text/chapter.xhtml"
    before = relocation_state(epub)
    with pytest.raises(ValueError, match="Package ID"):
        package.add_resource(Resource.from_bytes("new.png", b"x"), item_id="package-id")
    with pytest.raises(ValueError, match="already declared"):
        package.add_resource(epub.resources.by_path("OEBPS/text/chapter.xhtml"), item_id="other")
    with pytest.raises(ValueError, match="media type"):
        package.add_resource(Resource.from_bytes("new.png", b"x"), item_id="new", media_type="")
    assert relocation_state(epub) == before


def test_failed_inventory_add_rolls_back_declaration(tmp_path, monkeypatch):
    epub = make_epub(tmp_path)
    package = epub.package
    before = relocation_state(epub)

    def fail_add(self, resource):
        raise ValueError("inventory rejected addition")

    monkeypatch.setattr(ResourceIndex, "add", fail_add)
    with pytest.raises(ValueError, match="inventory rejected"):
        package.add_resource(Resource.from_bytes("new.png", b"x"), item_id="new")
    assert relocation_state(epub) == before
