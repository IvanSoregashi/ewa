"""Book-level link replacement: applies replace_links across all HTML-role
resources and reports replacement entries that never matched any document.
"""

from library.epub.recipe_html import replace_links
from library.epub.resources import ResourceIndex
from library.epub.utils_href import posix_relative_href


def replace_links_in_htmls(resources: ResourceIndex, replacement_dict: dict[str, str]) -> dict[str, str]:
    """Run replace_links on every resource. Returns the replacement entries
    that were never found and replaced in any document (e.g. orphan images
    that no chapter references)."""
    unmatched = replacement_dict.copy()
    for resource in resources:
        present_before = {
            old_link: posix_relative_href(resource.filename, old_link).encode("utf-8") in resource.content
            for old_link in unmatched
        }
        replace_links(resource, replacement_dict)
        for old_link, was_present in present_before.items():
            relative = posix_relative_href(resource.filename, old_link)
            if was_present and relative.encode("utf-8") not in resource.content:
                # the link was present in this document and is gone after the
                # replacement: the entry was found and replaced here
                del unmatched[old_link]
    return unmatched
