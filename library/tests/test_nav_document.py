import pytest
from pathlib import Path
from library.epub.xml_models.nav_model import NavDocument as PydanticNavDocument
from library.epub.xml_models.nav_schema import NavDocument as CustomNavDocument
from library.xml.utils import compare_roundtrip

SAMPLE_DIR = Path(__file__).parent / "samples" / "nav"
SAMPLE_XHTML = SAMPLE_DIR / "sample.xhtml"
ALL_SAMPLES = list(SAMPLE_DIR.glob("*.xhtml")) + list(SAMPLE_DIR.glob("*.html"))
ALL_NAV_DIR = Path("~").expanduser() / ".ewa" / "epub" / "nav"
ALL_NAV_PATHS = list(ALL_NAV_DIR.glob("*"))


@pytest.fixture(params=ALL_SAMPLES)
def nav_path(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture(params=[PydanticNavDocument, CustomNavDocument], ids=["PydanticNavDocument", "CustomNavDocument"])
def package_class(request: pytest.FixtureRequest) -> PydanticNavDocument:
    p_class: PydanticNavDocument = request.param
    return p_class


def test_nav_roundtrip(package_class, nav_path) -> None:
    assert compare_roundtrip(package_class, str(nav_path))


def test_read_nav(package_class):
    doc = package_class.from_path(str(SAMPLE_XHTML))
    assert doc.head.title == "toc.xhtml"
    assert len(doc.head.links) >= 1
    assert doc.head.links[0].href == "ebook.css"

    assert doc.body.nav.id == "toc"
    assert doc.body.nav.epub_type == "toc"
    assert doc.body.nav.h1.text == "Table of Contents"
    assert len(doc.body.nav.ol.items) >= 1

    item = doc.body.nav.ol.items[0]
    assert "TEST Verse Chapter 256 • | END |" == item.a.text
    assert "pages/test_chapter.xhtml" == item.a.href


def test_nav_edit(package_class):
    doc = package_class.from_path(str(SAMPLE_XHTML))

    # Edit title
    doc.head.title = "NEW TITLE"

    # Edit nav heading
    doc.body.nav.h1.text = "NEW HEADING"

    # Edit first list item
    item = doc.body.nav.ol.items[0]
    item.a.text = "UPDATED ITEM"
    item.a.href = "updated.xhtml"

    # Verify after re-parsing
    reparsed = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert reparsed.head.title == "NEW TITLE"
    assert reparsed.body.nav.h1.text == "NEW HEADING"
    assert reparsed.body.nav.ol.items[0].a.text == "UPDATED ITEM"
    assert reparsed.body.nav.ol.items[0].a.href == "updated.xhtml"


def test_nav_remove(package_class):
    doc = package_class.from_path(str(SAMPLE_XHTML))

    # Clear head metas and links
    doc.head.metas = []
    doc.head.links = []

    # Clear nav items (empty list) by removing the first one (it usually has elements in the sample)
    if len(doc.body.nav.ol.items) > 0:
        doc.body.nav.ol.remove_item(item=doc.body.nav.ol.items[0])

    # Verify after re-parsing
    reparsed = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert len(reparsed.head.metas) == 0
    assert len(reparsed.head.links) == 0
    assert len(reparsed.body.nav.ol.items) == 0


def test_nav_add(package_class):
    doc = package_class.from_path(str(SAMPLE_XHTML))

    # Add via method
    if package_class == PydanticNavDocument:
        from library.epub.xml_models.nav_model import NavLink as PNavLink

        link = PNavLink(href="new.xhtml", text="NEW ITEM")
    else:
        from library.epub.xml_models.nav_schema import NavLink as CNavLink

        link = CNavLink.create(href="new.xhtml", text="NEW ITEM")

    doc.body.nav.ol.add_item(link=link)

    # Verify after re-parsing
    reparsed = package_class.from_xml_bytes(doc.to_xml_bytes())
    assert len(reparsed.body.nav.ol.items) >= 2
    # The new item should be last
    assert reparsed.body.nav.ol.items[-1].a.text == "NEW ITEM"
    assert reparsed.body.nav.ol.items[-1].a.href == "new.xhtml"
