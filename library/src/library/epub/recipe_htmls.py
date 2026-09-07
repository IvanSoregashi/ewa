"""Book-level link replacement: applies replace_links across all HTML-role
resources and reports replacement entries that never matched any document.
"""

from library.epub.recipe_html import replace_links
from library.epub.resources import ResourceIndex
import logging

logger = logging.getLogger(__name__)


def replace_links_in_htmls(resources: ResourceIndex, replacement_dict: dict[str, str]) -> dict[str, str]:
    """Run replace_links on every resource. Returns the replacement entries
    that were never found and replaced in any document (e.g. orphan images
    that no chapter references)."""
    unmatched = replacement_dict.copy()
    replaced = dict()
    for resource in resources:
        replaced |= replace_links(resource, replacement_dict)

    return {k: v for k, v in unmatched.items() if k not in replaced}
