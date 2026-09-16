from library.epub.metadata import MetadataType
from library.epub.xml_models.package_metadata import Meta, Metadata
from library.epub.xml_models.package_sequences import Tours
from .test_package import make_epub


def test_document_ids_cover_sections_and_follow_edits_without_serialization(tmp_path, monkeypatch):
    document = make_epub(tmp_path).package.document
    document.id = "package"
    document.metadata.metas.append(Meta(id="metadata"))
    document.spine.id = "spine"
    document.spine.itemrefs[0].id = "spine-entry"
    document.tours = Tours()
    document.tours.add_tour(id="tour", title="Tour")

    def fail_serialization(*args, **kwargs):
        raise AssertionError("ID collection must not serialize XML")

    monkeypatch.setattr(type(document), "to_xml_tree", fail_serialization)
    assert {"package", "metadata", "spine", "spine-entry", "chapter", "tour"} <= document.ids
    document.metadata.metas[0].id = "changed"
    assert "metadata" not in document.ids
    assert "changed" in document.ids


def test_metadata_refinement_closure_and_identity_removal():
    metadata = Metadata()
    cover = Meta(name="cover", content="chapter")
    refinement = Meta(id="r1", refines="#chapter")
    indirect = Meta(refines="#r1")
    unrelated = Meta(name="other")
    cycle = Meta(id="cycle", refines="#cycle")
    metadata.metas = [indirect, cover, refinement, unrelated, cycle]
    targets = {"chapter"}
    selected = metadata.referencing(targets)
    assert {id(meta) for meta in selected} == {id(cover), id(refinement), id(indirect)}
    assert targets == {"chapter"}
    for meta in selected:
        metadata.remove_metadata(MetadataType.META, dc=False, item=meta)
    assert metadata.metas == [unrelated, cycle]
    assert metadata.referencing({"cycle"}) == [cycle]


def test_metadata_identity_removal_preserves_equal_sibling():
    first = Meta(refines="#chapter")
    second = Meta(refines="#chapter")
    metadata = Metadata(metas=[first, second])
    metadata.remove_metadata(MetadataType.META, dc=False, item=first)
    assert len(metadata.metas) == 1
    assert metadata.metas[0] is second
