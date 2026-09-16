from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import FileName
from library.epub.package_urls import path_url
from library.epub.utils_href import posix_relative_href


def relocate_package(epub: EPUB, target_package_path: str = FileName.DEFAULT_OPF) -> bool:
    """Move the opf to the archive root (content.opf) and rewrite every href
    inside it (manifest, guide) so it keeps resolving to the same resources.

    Content documents do not move, so nothing else needs fixing. Returns True
    if the opf was relocated.
    """
    return epub.package.relocate(target_package_path)


def replace_links(epub: EPUB, replace_dict: dict[str, str]) -> None:
    """Update manifest hrefs after resource renames.

    Args and keys are archive paths; the opf is expected to be standardized to
    the archive root (standardize_opf_location), where manifest hrefs coincide
    with archive paths. Media-type is refreshed from the renamed resource.
    """
    for old_link, new_link in replace_dict.items():
        item = require(epub.package.manifest_item_by_path(old_link), f"Manifest({old_link})")
        resource = require(epub.resources.by_path(new_link), f"Resource({new_link})")
        item.href = path_url(posix_relative_href(epub.package.resource.filename, new_link))
        item.media_type = str(resource.media_type)
