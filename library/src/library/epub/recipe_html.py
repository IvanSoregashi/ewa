from lxml.html import HtmlElement, document_fromstring

from library.epub.resources import Resource
from library.utils_xhtml import pretty_print


def translate_text(resource: Resource, table: dict) -> None:
    resource.content = resource.content.decode("utf-8", errors="replace").translate(table).encode("utf-8")


def replace_links(resource: Resource, table: dict[str, str]) -> None:
    html: HtmlElement = document_fromstring(resource.content)
    for element, attribute, link, pos in html.iterlinks():
        if link in table:
            element.set(attribute, table[link])
    resource.content = pretty_print(html)
