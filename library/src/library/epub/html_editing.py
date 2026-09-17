"""Reusable text and link edits on individual EPUB HTML resources."""

import logging

from lxml import etree
from lxml.html import document_fromstring

from library.epub.resources import Resource
from library.epub.utils_href import posix_absolute_href, posix_relative_href
from library.xml.utils import etree_from_bytes

logger = logging.getLogger(__name__)

_xml_parser = etree.XMLParser(huge_tree=True)

# href/src/poster/data in any namespace (plain href/src plus svg's xlink:href,
# object data, video poster), as smart strings carrying .getparent() and
# .attrname for write-back
_LINK_XPATH = etree.XPath(
    "//@*[local-name() = 'href' or local-name() = 'src' or local-name() = 'poster' or local-name() = 'data']"
)


def translate_text(resource: Resource, table: dict) -> None:
    resource.content = resource.content.decode("utf-8", errors="replace").translate(table).encode("utf-8")


def replace_links(
    resource: Resource, replacement_table: dict[str, str], pretty_print_result: bool = False
) -> dict[str, str]:
    try:
        html = etree_from_bytes(resource.content, _xml_parser)  # strict XML + self-healing
    except etree.XMLSyntaxError:
        html = document_fromstring(resource.content)  # lenient HTML fallback, still XML-serialized

    resource_filename = resource.filename
    replaced = {}
    for item in _LINK_XPATH(html):
        absolute_href = posix_absolute_href(resource_filename, str(item))
        new_link = replacement_table.get(absolute_href)
        if new_link is not None:
            relative_href = posix_relative_href(resource_filename, new_link)
            item.getparent().set(item.attrname, relative_href)
            replaced[absolute_href] = new_link

    resource.content = etree.tostring(
        html.getroottree(),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=pretty_print_result,
    )
    return replaced
