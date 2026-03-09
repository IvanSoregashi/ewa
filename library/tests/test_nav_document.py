import pytest
from pathlib import Path
from library.epub.xml_models.nav_model import NavDocument as PydanticNavDocument
from library.epub.xml_models.nav_schema import NavDocument as CustomNavDocument
from library.xml.utils import compare_roundtrip

SAMPLE_XHTML = Path(__file__).parent / "samples" / "sample.xhtml"


@pytest.fixture(
    params=[PydanticNavDocument, CustomNavDocument],
    ids=["PydanticNavDocument", "CustomNavDocument"]
)
def package_class(request: pytest.FixtureRequest) -> PydanticNavDocument:
    p_class: PydanticNavDocument = request.param
    return p_class


def test_nav_roundtrip(package_class):
    assert compare_roundtrip(package_class, str(SAMPLE_XHTML))

def test_nav_content(package_class):
    doc = package_class.from_path(str(SAMPLE_XHTML))
    assert doc.body.nav.id == "toc"
    assert len(doc.body.nav.ol.items) == 1

    item = doc.body.nav.ol.items[0]
    assert "TEST Verse Chapter 256 • | END |" == item.a.text
    assert "pages/test_chapter.xhtml" == item.a.href
