from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import FileName
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
    manifest = epub.core.manifest
    opf_path = epub.core.package_resource.filename
    for old_link, new_link in replace_dict.items():
        relative_old_link = posix_relative_href(opf_path, old_link)
        relative_new_link = posix_relative_href(opf_path, new_link)
        manifest_item = require(manifest.by_path(relative_old_link), f"Manifest({relative_old_link})")
        manifest_item.item.href = relative_new_link
        manifest_item.item.media_type = manifest_item.resource.media_type.value
