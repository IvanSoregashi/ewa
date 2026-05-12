from lxml import html, etree
from lxml.html import HtmlElement
from bs4 import BeautifulSoup, NavigableString
import json
import logging

from library.asserts import require

logger = logging.getLogger(__file__)


def from_html_head_parse_frontmatter(head: HtmlElement) -> dict:
    metadata_scripts = head.xpath('.//script[@id="frontmatter" and @type="application/ld+json"]')
    if metadata_scripts and metadata_scripts[0].text_content():
        return json.loads(metadata_scripts[0].text_content())
    return {}


def from_html_body_parse_first_header(body: HtmlElement) -> str | None:
    header = body.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6")
    if header:
        return header[0].text_content()
    return None


def from_html_body_parse_highest_header(body: HtmlElement) -> str | None:
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        found = body.find(f".//{tag}")
        if found is not None:
            return found.text_content()
    return None


def pretty_print(element: HtmlElement) -> bytes:
    return html.tostring(element, pretty_print=True)


def pretty_print_bytes(content: bytes) -> bytes:
    content = html.tostring(
        html.document_fromstring(content, parser=html.HTMLParser(remove_blank_text=True, remove_pis=True)),
        pretty_print=True,
    )
    return etree.tostring(
        etree.fromstring(content, parser=etree.XMLParser(remove_blank_text=True, remove_pis=True, recover=True)),
        pretty_print=True,
    )


def pretty_print_bs4_bytes(content: bytes) -> bytes:
    soup = BeautifulSoup(content, "html.parser")
    # soup = cleanup_calibre_formatting(soup)
    return soup.prettify(encoding="utf-8")


def cleanup_calibre_formatting(soup: BeautifulSoup) -> BeautifulSoup:
    # TODO requires more testing
    old_body = require(soup.body)
    old_text = set(old_body.get_text().strip().split())

    inline_tags = {"b", "i", "span", "em", "strong", "a"}
    new_body = soup.new_tag("body")

    current_paragraph = soup.new_tag("p")
    for node in list(old_body.contents):
        if isinstance(node, NavigableString):
            if current_paragraph.contents:
                current_paragraph.append(NavigableString("\n"))
            current_paragraph.append(node)
            continue

        if node.name == "p" and "calibre2" in node.get("class", []):
            if current_paragraph.contents:
                new_body.append(current_paragraph)
                new_body.append(NavigableString("\n"))
                current_paragraph = soup.new_tag("p")
            continue

        if node.name == "b" and "calibre3" in node.get("class", []) and not node.get_text().strip():
            continue

        if node.name in inline_tags:
            current_paragraph.append(node)
        else:
            if current_paragraph.contents:
                new_body.append(current_paragraph)
                new_body.append(NavigableString("\n"))
                current_paragraph = soup.new_tag("p")
            new_body.append(node)
            new_body.append(NavigableString("\n"))

    if current_paragraph.contents:
        new_body.append(current_paragraph)
        new_body.append(NavigableString("\n"))

    new_text = set(new_body.get_text().strip().split())
    assert old_text == new_text
    old_body.replace_with(new_body)
    return soup


def pretty_print_bytes_xml(content: bytes) -> bytes:
    return etree.tostring(
        etree.fromstring(content, parser=etree.XMLParser(remove_blank_text=True, remove_pis=True, recover=True)),
        pretty_print=True,
    )


def pretty_print_bytes_xml_html(content: bytes) -> bytes:
    return etree.tostring(
        etree.fromstring(content, parser=etree.HTMLParser(remove_blank_text=True, remove_pis=True, recover=True)),
        pretty_print=True,
    )
