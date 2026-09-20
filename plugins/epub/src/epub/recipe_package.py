from pathlib import Path

from epub.errors import InvalidEpubOutput
from epub.processing import ProcessingContext
from epub.protocols import EpubOperation
from library.asserts import require
from library.epub.epub import EPUB, EpubInfo
from library.epub.media_type import FileName
from library.epub.package_urls import path_url
from library.epub.utils_href import posix_relative_href


class PackageEpub(EpubOperation):
    def __init__(self, destination: str | Path) -> None:
        self.destination = destination

    def perform(self, context: ProcessingContext) -> None:
        context.epub.package_into(self.destination, sort_by_role=True)
        context.succeed(validate_epub_output(self.destination))


class DeclareMissingResources(EpubOperation):
    def perform(self, context: ProcessingContext) -> None:
        package = context.epub.package
        used_ids = package.document.ids
        number = 1
        for resource in package.undeclared_resources:
            while (item_id := f"resource-{number}") in used_ids:
                number += 1
            package.add_resource(resource, item_id=item_id)
            used_ids.add(item_id)


def validate_epub_output(path: str | Path) -> EpubInfo:
    """Only check reopening and metadata reading; full EPUB validation is pending."""
    try:
        return EPUB(path).info()
    except Exception as error:
        raise InvalidEpubOutput(str(error)) from error


def relocate_package(epub: EPUB, target_package_path: str = FileName.DEFAULT_OPF) -> bool:
    """Move the opf to the archive root (content.opf) and rewrite every href
    inside it (manifest, guide) so it keeps resolving to the same resources.

    Content documents do not move, so nothing else needs fixing. Returns True
    if the opf was relocated.
    """
    return epub.package.relocate(target_package_path)


def replace_links(epub: EPUB, replace_dict: dict[str, str]) -> dict[str, str]:
    """Update existing declarations and report missing old paths without adding entries.

    Mapping keys and values are archive paths; hrefs stay relative to the OPF.
    Media-type is refreshed from the renamed resource.
    """
    unmatched = {}
    for old_link, new_link in replace_dict.items():
        item = epub.package.manifest_item_by_path(old_link)
        if item is None:
            unmatched[old_link] = new_link
            continue
        resource = require(epub.resources.by_path(new_link), f"Resource({new_link})")
        item.href = path_url(posix_relative_href(epub.package.resource.filename, new_link))
        item.media_type = str(resource.media_type)
    return unmatched
