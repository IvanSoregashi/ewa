from zipfile import ZipFile

import pytest

from library.epub.epub import EPUB
from library.epub.media_type import EpubRole, MediaType
from library.epub.xml_models.package_sequences import ManifestItem


@pytest.mark.parametrize(
    "package_path, href, archive_path",
    [
        ("content.opf", "images/cover.jpg", "images/cover.jpg"),
        ("OEBPS/content.opf", "images/cover.jpg", "OEBPS/images/cover.jpg"),
        ("OEBPS/package/content.opf", "../images/cover.jpg", "OEBPS/images/cover.jpg"),
    ],
)
def test_manifest_resolves_relative_to_package(tmp_path, package_path, href, archive_path):
    path = tmp_path / "book.epub"
    opf = f'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>Test</dc:title>
      </metadata>
      <manifest><item id="picture" href="{href}" media-type="image/jpeg"/></manifest>
      <spine/>
    </package>'''
    with ZipFile(path, "w") as archive:
        archive.writestr(package_path, opf)
        archive.writestr(archive_path, b"image bytes")

    epub = EPUB(path)
    manifest = epub.core.manifest
    entry = manifest.by_id("picture")
    assert entry is not None
    assert entry.resource is epub.resources.by_path(archive_path)
    assert entry.resource.content == b"image bytes"
    assert entry.item.href == href
    assert manifest.by_path(href) is entry

    # A selection must retain the base used to resolve subsequently loaded items.
    for selection in (manifest.by_media_type(MediaType.IMAGE_JPEG), manifest.by_role(EpubRole.IMAGE)):
        assert selection.package is epub.package
        selection.add_opf_item(ManifestItem(id="another", href=href, media_type="image/jpeg"))
        assert selection.by_id("another").resource is entry.resource
