from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import FileName
from library.epub.utils_href import posix_absolute_href, posix_relative_href
from library.epub.xml_literals import FileTemplate


def relocate_package(epub: EPUB, target_package_path: str = FileName.DEFAULT_OPF) -> bool:
    """Move the opf to the archive root (content.opf) and rewrite every href
    inside it (manifest, guide) so it keeps resolving to the same resources.

    Content documents do not move, so nothing else needs fixing. Returns True
    if the opf was relocated.
    """
    package = epub.core.package
    package_resource = epub.core.package_resource
    current_package_path = package_resource.info.filename

    if current_package_path == target_package_path:
        return False

    for item in package.manifest.items:
        absolute = posix_absolute_href(current_package_path, item.href)
        item.href = posix_relative_href(target_package_path, absolute)

    if package.guide is not None:
        for reference in package.guide.references:
            absolute = posix_absolute_href(current_package_path, reference.href)
            reference.href = posix_relative_href(target_package_path, absolute)

    package_resource.filename = target_package_path
    package_resource.content = package.to_xml_bytes()

    # container must follow: it still points at the old opf location
    container_resource = epub.resources.by_path(FileName.CONTAINER)
    if container_resource is not None:
        container_resource.content = FileTemplate.CONTAINER.format(opf_path=target_package_path).encode("utf-8")
    return True


def replace_links(epub: EPUB, replace_links: dict[str, str]) -> None:
    """Update manifest hrefs after resource renames.

    Args and keys are archive paths; the opf is expected to be standardized to
    the archive root (standardize_opf_location), where manifest hrefs coincide
    with archive paths.
    """
    manifest = epub.core.manifest
    for old_link, new_link in replace_links.items():
        manifest_item = require(manifest.by_path(old_link), f"Manifest({old_link})")
        manifest_item.item.href = new_link
