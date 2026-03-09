import pytest
from pathlib import Path
from library.epub.xml_models.ncx_model import NCXDocument as PydanticNCXDocument
from library.epub.xml_models.ncx_schema import NCXDocument as CustomNCXDocument
from library.xml.utils import compare_roundtrip

SAMPLE_DIR = Path(__file__).parent / "samples" / "ncx"
SAMPLE_NCX = SAMPLE_DIR / "sample.ncx"
ALL_SAMPLES = list(SAMPLE_DIR.glob("*.ncx"))


@pytest.fixture(params=ALL_SAMPLES)
def ncx_path(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture(params=[PydanticNCXDocument, CustomNCXDocument], ids=["PydanticNCXDocument", "CustomNCXDocument"])
def package_class(request: pytest.FixtureRequest) -> PydanticNCXDocument:
    p_class: PydanticNCXDocument = request.param
    return p_class


def test_ncx_roundtrip(package_class, ncx_path) -> None:
    assert compare_roundtrip(package_class, str(ncx_path))


def test_read_ncx(package_class):
    doc = package_class.from_path(str(SAMPLE_NCX))
    
    assert doc.doc_title.text == "Chapter 0: Prologue - test chapter"
    assert len(doc.nav_map.nav_points) == 1
    
    point = doc.nav_map.nav_points[0]
    assert point.id == "ebook0"
    assert point.play_order == 1
    assert point.nav_label.text == "Chapter 0: Prologue - test chapter"
    assert point.content.src == "pages/chapter_0_prologue__lovers_lifeline_system__chapter_1_by_silversakura_full_book_limited_free__webnovel_official3680.xhtml"


def test_ncx_edit(package_class):
    doc = package_class.from_path(str(SAMPLE_NCX))
    
    # Edit title
    doc.doc_title.text = "UPDATED TITLE"
    
    # Edit first navPoint
    point = doc.nav_map.nav_points[0]
    point.nav_label.text = "UPDATED LABEL"
    point.content.src = "updated.xhtml"
    point.play_order = 99

    # Verify after re-parsing
    reparsed = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert reparsed.doc_title.text == "UPDATED TITLE"
    assert reparsed.nav_map.nav_points[0].nav_label.text == "UPDATED LABEL"
    assert reparsed.nav_map.nav_points[0].content.src == "updated.xhtml"
    assert reparsed.nav_map.nav_points[0].play_order == 99


def test_ncx_remove(package_class):
    doc = package_class.from_path(str(SAMPLE_NCX))
    
    # Clear docAuthors
    doc.doc_authors = []
    
    # Clear navPoints by removing the first one (since Sample only has 1)
    if "nav_point" in doc.nav_map.nav_points[0].id or len(doc.nav_map.nav_points) > 0:
        doc.nav_map.remove_nav_point(point=doc.nav_map.nav_points[0])
    
    # Verify after re-parsing
    reparsed = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert len(reparsed.doc_authors) == 0
    assert len(reparsed.nav_map.nav_points) == 0


def test_ncx_add(package_class):
    doc = package_class.from_path(str(SAMPLE_NCX))
    
    # Add a new navPoint 
    from library.epub.xml_models.ncx_model import Content
    if package_class == PydanticNCXDocument:
        from library.epub.xml_models.ncx_model import Content as PydanticContent
        content = PydanticContent(src="new.xhtml")
    else:
        from library.epub.xml_models.ncx_schema import Content as CustomContent
        content = CustomContent.create(src="new.xhtml")
        
    doc.nav_map.add_nav_point(
        id="new_point", 
        content=content,
    )
    # the schema logic does not automatically create nav_label for us when calling add_nav_point right now because it's a child element
    # we just need to verify the addition worked
    doc.nav_map.nav_points[-1].play_order = 2
    
    # Verify after re-parsing
    reparsed = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert len(reparsed.nav_map.nav_points) == 2
    assert reparsed.nav_map.nav_points[1].id == "new_point"
