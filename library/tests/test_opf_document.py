import random
from pathlib import Path

import pytest

from library.epub.xml_models.opf_model import PackageDocument as PydanticPackageDocument, Metadata as PydanticMetadata, Manifest as PydanticManifest, Spine as PydanticSpine, Guide as PydanticGuide, Tours as PydanticTours
from library.epub.xml_models.opf_schema import PackageDocument as CustomPackageDocument, Metadata as CustomMetadata, Manifest as CustomManifest, Spine as CustomSpine, Guide as CustomGuide, Tours as CustomTours
from library.xml.utils import compare_roundtrip

SAMPLE_DIR = Path(__file__).parent / "samples" / "opf"
SAMPLE_OPF = SAMPLE_DIR / "sample.opf"
ALL_SAMPLES = [p for p in SAMPLE_DIR.glob("*.opf") if not p.name.endswith(".formatted.opf")]
ALL_OPF_DIR = Path("~").expanduser() / ".ewa" / "epub" / "opf"
ALL_OPF_PATHS = list(ALL_OPF_DIR.glob("*.opf"))


@pytest.fixture(params=ALL_SAMPLES)
def opf_path(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture(
    params=[PydanticPackageDocument, CustomPackageDocument], ids=["PydanticPackageDocument", "CustomPackageDocument"]
)
def package_class(request: pytest.FixtureRequest) -> PydanticPackageDocument:
    p_class: PydanticPackageDocument = request.param
    return p_class


def test_opf_roundtrip(package_class, opf_path):
    assert compare_roundtrip(package_class, str(opf_path))


def test_opf_literal_comparison(package_class, opf_path):
    import difflib

    suffix = ".pydantic.formatted.opf" if package_class == PydanticPackageDocument else ".custom.formatted.opf"
    formatted_path = opf_path.with_suffix(suffix)
    if not formatted_path.exists():
        pytest.skip(f"No formatted file for {opf_path} with {suffix}")

    expected_content = formatted_path.read_text(encoding="utf-8").strip()
    doc = package_class.from_path(str(opf_path))
    actual_content = doc.to_xml_bytes(pretty_print=True).decode("utf-8").strip()

    if actual_content != expected_content:
        diff = difflib.unified_diff(
            expected_content.splitlines(),
            actual_content.splitlines(),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
        print(f"\nLiteral diff for {opf_path.name} ({package_class.__name__}):")
        for line in diff:
            print(line)
        assert actual_content == expected_content


def test_read_opf_metadata(package_class):
    doc: PydanticPackageDocument = package_class.from_path(str(SAMPLE_OPF))

    assert doc.metadata.title.text == "TEST TITLE 9"
    assert doc.metadata.language.text == "en"

    assert len(doc.metadata.descriptions) == 1
    assert doc.metadata.descriptions[0].text == (
        '<div><span style="color: rgb(51, 51, 51); font-family: Arial, sans-serif; '
        'orphans: 2; widows: 2; background-color: rgb(255, 255, 255);">TEST '
        'DESCRIPTION 1</span><br style="color: rgb(51, 51, 51); font-family: Arial, '
        "sans-serif; orphans: 2; widows: 2; background-color: rgb(255, 255, "
        '255);"><br style="color: rgb(51, 51, 51); font-family: Arial, sans-serif; '
        'orphans: 2; widows: 2; background-color: rgb(255, 255, 255);"><span '
        'style="color: rgb(51, 51, 51); font-family: Arial, sans-serif; orphans: 2; '
        'widows: 2; background-color: rgb(255, 255, 255);">TEST DESCRIPTION '
        '2</span><br style="color: rgb(51, 51, 51); font-family: Arial, sans-serif; '
        'orphans: 2; widows: 2; background-color: rgb(255, 255, 255);"><br '
        'style="color: rgb(51, 51, 51); font-family: Arial, sans-serif; orphans: 2; '
        'widows: 2; background-color: rgb(255, 255, 255);"><span style="color: '
        "rgb(51, 51, 51); font-family: Arial, sans-serif; orphans: 2; widows: 2; "
        'background-color: rgb(255, 255, 255);">TEST DESCRIPTION 3</span></div>'
    )

    assert len(doc.metadata.creators) == 1
    assert doc.metadata.creators[0].text == "TEST AUTHOR"
    assert doc.metadata.creators[0].file_as_ns == "AUTHOR, TEST"
    assert doc.metadata.creators[0].role_ns == "aut"
    assert doc.metadata.dates[0].text == "2020-05-15T04:00:00+00:00"


def test_read_opf_manifest(package_class):
    doc: PydanticPackageDocument = package_class.from_path(str(SAMPLE_OPF))
    assert len(doc.manifest.items) == 23

    # Check specific attributes to ensure descriptors work
    item = doc.manifest.items[0]
    assert item.id == "cover"
    assert item.href == "cover.jpeg"
    assert item.media_type == "image/jpeg"


def test_read_opf_spine(package_class):
    doc: PydanticPackageDocument = package_class.from_path(str(SAMPLE_OPF))
    assert len(doc.spine.itemrefs) == 18
    ref = doc.spine.itemrefs[0]
    assert ref.idref == "titlepage"
    assert ref.linear is None  # Should be optional


def test_read_opf_guide(package_class):
    doc: PydanticPackageDocument = package_class.from_path(str(SAMPLE_OPF))
    assert doc.guide is not None
    assert len(doc.guide.references) == 1
    ref = doc.guide.references[0]
    assert ref.type == "cover"
    assert ref.title == "Cover"
    assert ref.href == "titlepage.xhtml"


def test_opf_metadata_add(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    metadata = doc.metadata

    # Add Creator with attributes
    metadata.add_metadata("creator", "NEW AUTHOR", id="author_1", role_ns="aut", file_as_ns="AUTHOR, NEW")
    # Add Meta with attributes (EPUB 3)
    metadata.add_metadata("meta", "2024-01-01T00:00:00Z", dc=False, property="dcterms:modified", id="mod_1")
    # Add Identifier with scheme
    metadata.add_metadata("identifier", "987654321", scheme_ns="ISBN", id="isbn_id")

    # Verify after re-parsing
    new_doc = package_class.from_xml_bytes(doc.to_xml_bytes())
    new_meta = new_doc.metadata

    author = next(c for c in new_meta.creators if c.text == "NEW AUTHOR")
    assert author.id == "author_1"
    assert author.role_ns == "aut"
    assert author.file_as_ns == "AUTHOR, NEW"

    mod = next(m for m in new_meta.metas if m.text == "2024-01-01T00:00:00Z")
    assert mod.property == "dcterms:modified"
    assert mod.id == "mod_1"

    isbn = next(i for i in new_meta.identifiers if i.text == "987654321")
    assert isbn.scheme_ns == "ISBN"


def test_opf_metadata_modify(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    metadata = doc.metadata

    # Modify existing title and its text/attributes
    title_elem = metadata.titles[0]
    title_elem.text = "UPDATED TITLE"
    title_elem.lang = "ru"

    # Modify existing identifier's scheme
    ident = metadata.identifiers[0]
    ident.scheme_ns = "NEW_SCHEME"

    # Verify after re-parsing
    new_doc = package_class.from_xml_bytes(doc.to_xml_bytes())
    new_meta = new_doc.metadata

    assert new_meta.titles[0].text == "UPDATED TITLE"
    assert new_meta.titles[0].lang == "ru"
    assert new_meta.identifiers[0].scheme_ns == "NEW_SCHEME"


def test_opf_manifest_edit(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    item = doc.manifest.items[0]
    item.href = "new_cover.jpg"
    item.media_type = "image/png"
    item.id = "new_cover_id"

    new_doc = package_class.from_xml_bytes(doc.to_xml_bytes())
    new_item = new_doc.manifest.items[0]
    assert new_item.href == "new_cover.jpg"
    assert new_item.media_type == "image/png"
    assert new_item.id == "new_cover_id"


def test_opf_spine_edit(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    ref = doc.spine.itemrefs[0]
    ref.idref = "new_idref"
    ref.linear = "no"

    new_doc = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert new_doc.spine.itemrefs[0].idref == "new_idref"
    assert new_doc.spine.itemrefs[0].linear == "no"


def test_opf_manifest_add_remove(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    initial_count = len(doc.manifest.items)
    
    # Add
    doc.manifest.add_item(id="added-item", href="added.xhtml", media_type="application/xhtml+xml")
    assert len(doc.manifest.items) == initial_count + 1
    
    # Remove
    doc.manifest.remove_item(id="added-item")
    assert len(doc.manifest.items) == initial_count


def test_opf_spine_add_remove(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    initial_count = len(doc.spine.itemrefs)
    
    # Add
    doc.spine.add_itemref(idref="added-ref", linear="yes")
    assert len(doc.spine.itemrefs) == initial_count + 1
    
    # Remove
    doc.spine.remove_itemref(idref="added-ref")
    assert len(doc.spine.itemrefs) == initial_count


def test_opf_guide_add_remove(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    if doc.guide is None:
        # If missing, we'd need a guide class to create it, 
        # but SAMPLE_OPF has a guide.
        pass
    
    initial_count = len(doc.guide.references)
    added_ref = doc.guide.add_reference(type="title-page", href="title.xhtml", title="Title Page")
    assert len(doc.guide.references) == initial_count + 1
    
    doc.guide.remove_reference(reference=added_ref)
    assert len(doc.guide.references) == initial_count


def test_opf_sections_missing_initial(package_class):
    # Create minimal OPF from bytes (with only package/metadata/manifest/spine)
    # Most readers require these anyway.
    minimal_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">-</dc:identifier></metadata>'
        '<manifest></manifest>'
        '<spine></spine>'
        '</package>'
    ).encode("utf-8")
    
    doc = package_class.from_xml_bytes(minimal_xml)
    
    # Verify these exist as empty lists/objects
    assert len(doc.manifest.items) == 0
    assert len(doc.spine.itemrefs) == 0
    
    # Test adding to initially empty
    doc.manifest.add_item(id="item1", href="1.xhtml", media_type="text/html")
    doc.spine.add_itemref(idref="item1")
    
    new_doc = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert len(new_doc.manifest.items) == 1
    assert len(new_doc.spine.itemrefs) == 1


def test_opf_add_missing_sections(package_class):
    # Create invalid OPF without manifest/spine
    minimal_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">-</dc:identifier></metadata>'
        '</package>'
    ).encode("utf-8")
    
    if package_class == PydanticPackageDocument:
        # Pydantic is strict and throws on missing mandatory sections during parse
        with pytest.raises(Exception):
            package_class.from_xml_bytes(minimal_xml)
    else:
        # Custom is currently lenient (returns None for missing ChildField)
        doc = package_class.from_xml_bytes(minimal_xml)
        assert doc.manifest is None
        assert doc.spine is None
        
        # We can add them manually
        doc.manifest = CustomManifest.create()
        doc.spine = CustomSpine.create()
        
        doc.manifest.add_item(id="i1", href="h1.html", media_type="text/html")
        doc.spine.add_itemref(idref="i1")
        
        # Verify
        new_doc = package_class.from_xml_bytes(doc.to_xml_bytes())
        assert len(new_doc.manifest.items) == 1
        assert len(new_doc.spine.itemrefs) == 1


def test_opf_create_from_scratch(package_class):
    # Test programmatic creation without parsing
    if package_class == PydanticPackageDocument:
        # Mandatory fields must be provided to constructor
        meta = PydanticMetadata()
        doc = PydanticPackageDocument(
            version="2.0", 
            unique_identifier="id", 
            metadata=meta,
            manifest=PydanticManifest(),
            spine=PydanticSpine()
        )
        doc.metadata.add_metadata("identifier", "978...", id="id")
    else:
        # Custom can be created empty and filled
        doc = CustomPackageDocument.create(version="2.0")
        doc.metadata = CustomMetadata.create()
        doc.manifest = CustomManifest.create()
        doc.spine = CustomSpine.create()
        doc.metadata.add_metadata("identifier", "978...", id="id")

    doc.manifest.add_item(id="item1", href="1.xhtml", media_type="text/html")
    doc.spine.add_itemref(idref="item1")
    
    xml = doc.to_xml_bytes()
    new_doc = package_class.from_xml_bytes(xml)
    assert len(new_doc.manifest.items) == 1
    assert len(new_doc.spine.itemrefs) == 1


def test_opf_metadata_remove(package_class):
    doc = package_class.from_path(str(SAMPLE_OPF))
    metadata = doc.metadata

    # Remove all subjects and creators
    metadata.remove_metadata("subject")
    metadata.remove_metadata("creator")

    # Verify after re-parsing
    new_doc = package_class.from_xml_bytes(doc.to_xml_bytes())
    new_meta = new_doc.metadata

    assert len(new_meta.subjects) == 0
    assert len(new_meta.creators) == 0
    # Other metadata should remain
    assert len(new_meta.titles) > 0
