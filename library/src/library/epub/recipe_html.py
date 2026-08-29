from lxml.html import HtmlElement, document_fromstring

from library.epub.resources import Resource
from library.epub.utils_href import posix_relative_href
from library.utils_xhtml import pretty_print


def translate_text(resource: Resource, table: dict) -> None:
    resource.content = resource.content.decode("utf-8", errors="replace").translate(table).encode("utf-8")


def replace_links(resource: Resource, table: dict[str, str]) -> None:
    """Rewrite links according to `table`.

    The table maps ARCHIVE paths (old -> new), e.g. the image rename dictionary.
    Document links are resolved relative to the document's own location before
    matching, and the replacement is written relative to the document again.
    """
    html: HtmlElement = document_fromstring(resource.content)
    resource_filename = resource.filename
    table_for_resource = {
        posix_relative_href(resource_filename, old_link): posix_relative_href(resource_filename, new_link)
        for old_link, new_link in table.items()
    }
    for element, attribute, link, pos in html.iterlinks():
        if link in table_for_resource:
            element.set(attribute, table_for_resource[link])
    resource.content = pretty_print(html)
