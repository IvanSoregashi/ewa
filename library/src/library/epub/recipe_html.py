from lxml import etree
from lxml.html import HtmlElement, document_fromstring

from library.epub.resources import Resource
from library.epub.utils_href import posix_relative_href

_xml_parser = etree.XMLParser(huge_tree=True)
_xml_parser.set_element_class_lookup(etree.ElementDefaultClassLookup(element=HtmlElement))


def translate_text(resource: Resource, table: dict) -> None:
    resource.content = resource.content.decode("utf-8", errors="replace").translate(table).encode("utf-8")


def replace_links(resource: Resource, table: dict[str, str], pretty_print_result: bool = False) -> None:
    """Rewrite links according to `table`.

    The table maps ARCHIVE paths (old -> new), e.g. the image rename dictionary.
    Document links are resolved relative to the document's own location before
    matching, and the replacement is written relative to the document again.

    The chapter is parsed as XML and serialized back as XML: void elements stay
    self-closed (`<br/>`), the XML declaration and namespaces survive, so the
    result remains valid parseable XML (see verification.verify_chapter_xml).
    Documents that are not well-formed XML (e.g. named entities without a DTD)
    fall back to the lenient HTML parser - the output is still XML-serialized.
    `pretty_print_result` toggles serializer indentation only.
    """
    try:
        html: HtmlElement = etree.fromstring(resource.content, _xml_parser)
    except etree.XMLSyntaxError:
        html = document_fromstring(resource.content)

    resource_filename = resource.filename

    table_for_resource = {
        posix_relative_href(resource_filename, old_link): posix_relative_href(resource_filename, new_link)
        for old_link, new_link in table.items()
    }

    for element, attribute, link, pos in html.iterlinks():
        if link in table_for_resource:
            element.set(attribute, table_for_resource[link])

    resource.content = etree.tostring(
        html.getroottree(),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=pretty_print_result,
    )
