import random
from pathlib import Path

import pytest

from library.epub.xml_models.opf_model import PackageDocument as PydanticPackageDocument
from library.epub.xml_models.opf_schema import PackageDocument as CustomPackageDocument
from library.xml.utils import compare_roundtrip

SAMPLE_OPF = Path(__file__).parent / "samples" / "sample.opf"
random_txt = Path(__file__).parent / "samples" / (str(random.randint(1000000, 9999999)) + "_result.opf")
ALL_OPF_DIR = Path("~").expanduser() / ".ewa" / "epub" / "opf"
ALL_OPF_PATHS = list(ALL_OPF_DIR.glob("*.opf"))
NAMESPACE_ISSUE = [
    r"C:\Users\Ivan\.ewa\epub\opf\daed016fdcd99ae496089be4e02087a2_content.opf",
    r"C:\Users\Ivan\.ewa\epub\opf\609946ca1f662a890dbe1a350c619cac_content.opf",
    r"C:/Users/Ivan/.ewa/epub/opf/57658a80f2b350c9b5f80ee3485d6015_content.opf",
    r"C:/Users/Ivan/.ewa/epub/opf/52a0128cbe4ac4a4179fb8a2ca91b2b4_content.opf",
    r"C:/Users/Ivan/.ewa/epub/opf/3d130f8fb66838cf8018f0701f88dca3_content.opf"
]

@pytest.fixture(params=NAMESPACE_ISSUE)
def opf_ns_issue_path(request: pytest.FixtureRequest) -> str:
    return str(request.param)

@pytest.fixture(params=ALL_OPF_PATHS)
def opf_path(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture(
    params=[PydanticPackageDocument, CustomPackageDocument],
    ids=["PydanticPackageDocument", "CustomPackageDocument"]
)
def package_class(request: pytest.FixtureRequest) -> PydanticPackageDocument:
    p_class: PydanticPackageDocument = request.param
    return p_class


def test_opf_roundtrip(package_class, opf_ns_issue_path):
    assert compare_roundtrip(package_class, str(opf_ns_issue_path))


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
