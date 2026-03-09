from pathlib import Path

import pytest

from library.epub.xml_models.ncx_model import NCXDocument as PydanticNCXDocument
from library.epub.xml_models.ncx_schema import NCXDocument as CustomNCXDocument
from library.xml.utils import compare_roundtrip

SAMPLE_NCX = Path(__file__).parent / "samples" / "sample.ncx"


@pytest.fixture(params=[PydanticNCXDocument, CustomNCXDocument], ids=["PydanticNCXDocument", "CustomNCXDocument"])
def package_class(request: pytest.FixtureRequest) -> PydanticNCXDocument:
    p_class: PydanticNCXDocument = request.param
    return p_class


def test_ncx_roundtrip(package_class):
    assert compare_roundtrip(package_class, str(SAMPLE_NCX))


def test_ncx_content(package_class):
    doc = package_class.from_path(str(SAMPLE_NCX))
    assert doc.doc_title.text == "Chapter 0: Prologue - test chapter"
    assert len(doc.nav_map.nav_points) == 1

    point = doc.nav_map.nav_points[0]
    assert point.id == "ebook0"
    assert point.play_order == 1
    assert point.nav_label.text == "Chapter 0: Prologue - test chapter"
