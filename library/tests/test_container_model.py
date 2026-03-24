from pathlib import Path

import pytest

from library.epub.xml_models.container_model import ContainerDocument as ContainerModel
from library.epub.xml_models.container_schema import ContainerDocument as ContainerSchema

SAMPLE_DIR = Path(__file__).parent / "samples" / "container"
ALL_SAMPLES = [p for p in SAMPLE_DIR.glob("*.xml")]
path_to_opf = {
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\07736700aa1ca4b54c78ab071c37b23a_container.xml": "book.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\0a62f46d048d61e183190d115c71f949_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\112848f1de07567a516d4500e8c72bfb_container.xml": "book.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\12911c64619e1257e6845feee49c17b6_container.xml": "book.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\12ee02d9a9c9fbaab5b4dce22120eaf5_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\1445bde2f4bed7bac9e6254d2591cb16_container.xml": "OEBPS/document.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\157af0ab2e70d8b1ef431b75caf4bff3_container.xml": "OEBPS/book.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\175ebe5c1506d0c3d2872259a634479b_container.xml": "OPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\1b5af9b733501fdb66a49fd59de94bc6_container.xml": "EPUB/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\1e3d64ff79ed2a77edc208928bca4e0b_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\25c6a23037ab062484283afd8db43ca5_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\29cbecb2b406c2d26730d948c79dfa93_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\2ec1de232bcb2d592377e9e6c8b7623f_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\34c0931ff43433c40a9dd8ab7cb2ec0a_container.xml": "Hami_9780345495518_epub_opf_r1.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\34e4f64b779ef4ef59ad5e03ec1b9c44_container.xml": "EPUB/package.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\34f9b8c9526ed8c1459421b4fb35a56a_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\3a918432032ecc0990b5d1bc7f1f12b7_container.xml": "OEBPS/opf.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\3c453de2bcc91571668d0fe5d363ea45_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\405fd6fa693c6b84aa82c50fe45b2647_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\40d53099d2ff79756c0708dfde231185_container.xml": "OPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\477e92dc87482101fbc5265755301087_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\49c8243efab9c99d19356e9fe37eeabc_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\4a28b4c394a98bec520da48dc6bfab82_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\4b22d738f43b2ca482e48d0aca3aa7b8_container.xml": "OPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\4c37724782a453d8a33b7f38a5a1fc23_container.xml": "OEBPF/ebook.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\4d88cedea30780d86f57c38d728f4df9_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\565e381bcc16ce7c018b7f53a03e7a1c_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\5776da478d49e3f5cdc148e729fa5d71_container.xml": "OEBPS/predictablyirrationalrevisedandexpandededition.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\58bb75a096f32d112f353cfcd05d2d3a_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\59a21f3c15ff04fffb087358ba984ce8_container.xml": "OPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\5c01fabe2780873a02c10c803a2885d2_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\6319727d7a78a7ce95f3119f8a3bce1a_container.xml": "OEBPS/package.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\635461743ffabccf0685935c2bd653cf_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\66809a3e980c7c3a9f786178a54a5931_container.xml": "EPUB/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\67b64ffabe2b63b52ba9571152bbaab8_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\67c6d16fe95ee61260e9f1cfafe759b5_container.xml": "OPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\74d0a171c13584304e4b14f73fe9612d_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\7a7522dcf8dfb59a87db34fc810fdcf9_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\7e1a77900a2d22aad56f143cdb7f5858_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\81f80b26189d6032dd0f2dc2d6564fd0_container.xml": "OEBPS/Content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\81fe74250b0c45a6b2453a9d346578d7_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\8f9da5fcb4412f7de2fac9393211bc88_container.xml": "OPS/fb.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\996f05b49246d0cf73f32c4f6f9c2522_container.xml": "OEBPS/package.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\9fc99eed39939b86068d1fc3b3501ce5_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\aaf53f475c12e848830b444e72dd7b3a_container.xml": "OEBPS/ConfederationH_opf.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\bb337a3b09d299bd2d9d0d4c99172594_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\bc99b0855b76d340d348a0d3985b70f8_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\be97acec0a29725d83f5c555fe4002e1_container.xml": "OPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\bf7954a99a97ad73d586069ba503cd55_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\c25e15f0617ef3044af917c2c1e62c94_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\c3834e7773d6991c12e3560bd0cfc22a_container.xml": "8800/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\c9694d43facdfbbbce0e41bc516ae797_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\cb36c991c7709f9437bb7517c759af76_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\ce8b71f9deff03505fad264e62346a8a_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\d3efb148aec87878e1bebe223f8480ed_container.xml": "OPS/ibooks.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\d6ce537a9dae180eb510852e3b8248c2_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\d6d5bdf447a0157161d69362addad362_container.xml": "EPUB/package.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\d7096d936aa0c1e8a6b4c10645ac2791_container.xml": "OPS/epb.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\d75234e7da1215905742627b48e0f6a9_container.xml": "EPUB/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\d7b429581dbecf0b3a6177f03b82bbaf_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\d7fd908943a97beaf91f91ca356c5849_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\e0d9484dde51e8b5df08ba3ddceef909_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\e209e21064d37de63720e6262d5033f3_container.xml": "GoogleDoc/package.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\e615997296b35fe1c2afb8b67c2e5fb4_container.xml": "OPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\ecb4ea89ea19056dbfbe091e9e406e02_container.xml": "EPUB/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\ed420a1ddad9fdee076a138162b647df_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\f101ba51f63e4cd646ffdd6751f85d7a_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\f57b13ca0d040351d4343080d14f29fd_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\f6b3e8fbd2ad0be0250d1d8fc2c4e8f1_container.xml": "content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\fb9c89778798fc6e4f5b8b8657b318eb_container.xml": "Hami_9780804180658_epub_opf_r1.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\fd3f42074192ae408914519a6ac859db_container.xml": "OEBPS/content.opf",
    "C:\\Users\\Ivan\\Projects\\ewa\\library\\tests\\samples\\container\\fdb0aeb3d20d68c0a0bd252c53642922_container.xml": "OEBPS/content.opf",
}


@pytest.fixture(params=ALL_SAMPLES)
def container_path(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture(params=[ContainerModel, ContainerSchema], ids=["PydanticContainerDocument", "CustomContainerDocument"])
def package_class(request: pytest.FixtureRequest) -> ContainerModel:
    p_class: ContainerModel = request.param
    return p_class


def test_containers(package_class: ContainerModel, container_path: Path):
    path = str(container_path)
    assert package_class.from_path(path).opf_path == path_to_opf[path]
