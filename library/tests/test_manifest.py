from zipfile import ZipFile

import pytest

from library.epub.epub import EPUB
from library.epub.media_type import EpubRole, MediaType


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
    package = epub.package
    entry = package.document.manifest.find_item(id="picture")
    assert entry is not None
    resource = package.resource_for_href(entry.href)
    assert resource is epub.resources.by_path(archive_path)
    assert resource.content == b"image bytes"
    assert entry.href == href
    assert package.manifest_item_by_path(archive_path) is entry
    assert tuple(package.manifest_resources.by_media_type(MediaType.IMAGE_JPEG)) == (resource,)
    assert tuple(package.manifest_resources.by_role(EpubRole.IMAGE)) == (resource,)
