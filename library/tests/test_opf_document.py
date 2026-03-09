import random
from pathlib import Path

import pytest

from library.epub.xml_models.opf_model import PackageDocument as PydanticPackageDocument
from library.epub.xml_models.opf_schema import PackageDocument as CustomPackageDocument
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
    params=[PydanticPackageDocument, CustomPackageDocument],
    ids=["PydanticPackageDocument", "CustomPackageDocument"]
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
            lineterm=""
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
