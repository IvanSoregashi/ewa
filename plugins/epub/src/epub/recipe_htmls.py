"""Book-level link replacement: applies replace_links across all HTML-role
resources and reports replacement entries that never matched any document.
"""

from epub.processing import ProcessingContext
from epub.recipe_package import replace_manifest_links
from library.epub.media_type import EpubRole, MediaType
from epub.protocols import EpubOperation
from library.epub.html_editing import replace_links, translate_text
from library.epub.resources import ResourceSelection
import logging


logger = logging.getLogger(__name__)


def replace_links_in_htmls(resources: ResourceSelection, replacement_dict: dict[str, str]) -> dict[str, str]:
    """Run replace_links on every resource. Returns the replacement entries
    that were never found and replaced in any document (e.g. orphan images
    that no chapter references)."""
    unmatched = replacement_dict.copy()
    replaced = dict()
    for resource in resources:
        replaced |= replace_links(resource, replacement_dict)

    return {k: v for k, v in unmatched.items() if k not in replaced}


class ReplaceLinks(EpubOperation):
    """Update HTML/OPF and report their unmatched paths separately for verification."""

    def perform(self, context: ProcessingContext) -> None:
        if not context.replacements:
            return
        epub = context.epub
        context.unmatched_links = replace_links_in_htmls(epub.resources.by_role(EpubRole.HTML), context.replacements)
        context.unmatched_manifest_links = replace_manifest_links(epub, context.replacements)
        context.replacements.clear()


class TextTranslator(EpubOperation):
    def __init__(self, replacement_dict: dict) -> None:
        self.replacement_dict = replacement_dict

    def perform(self, context: ProcessingContext) -> None:
        for resource in context.epub.resources.by_role(EpubRole.HTML):
            translate_text(resource, self.replacement_dict)


class RemoveResourceAndManifest(EpubOperation):
    def __init__(
        self,
        role: EpubRole | None = None,
        media_type: MediaType | None = None,
        path: str | None = None,
        exact_path: str | None = None,
        flush: bool = True,
    ) -> None:
        self.role = role
        self.media_type = media_type
        self.exact_path = exact_path
        self.path = path
        self.flush = flush

    def perform(self, context: ProcessingContext) -> None:
        epub = context.epub
        resources = epub.resources

        if self.role is not None:
            resources = resources.by_role(self.role)
        if self.media_type is not None:
            resources = resources.by_media_type(self.media_type)
        if self.path is not None:
            resources = [resource for resource in resources if self.path in resource.filename.lower()]
        elif self.exact_path is not None:
            resources = [resource for resource in resources if resource.filename == self.exact_path]

        for resource in list(resources):
            epub.package.remove_resource(resource)

        if self.flush:
            epub.package.flush()
