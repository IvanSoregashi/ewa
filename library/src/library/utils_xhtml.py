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


def is_empty_calibre_tag(tag) -> bool:
    if tag.name != "p":
        return False
    classes = tag.get("class", [])
    if not any("calibre" in str(c) for c in classes):
        return False
    text = tag.get_text().strip()
    return not text or text == "\xa0"


def cleanup_calibre_formatting(soup: BeautifulSoup) -> BeautifulSoup:
    old_body = require(soup.body)
    old_text = set(old_body.get_text().strip().split())

    new_body = soup.new_tag("body")
    current_paragraph = None

    def flush_paragraph():
        nonlocal current_paragraph
        if current_paragraph and current_paragraph.contents:
            new_body.append(current_paragraph)
            new_body.append(NavigableString("\n"))
            current_paragraph = None

    for node in list(old_body.children):
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if not text:
                continue
            if current_paragraph is None:
                current_paragraph = soup.new_tag("p")
            current_paragraph.append(NavigableString(text))
            continue

        if node.name == "p":
            if is_empty_calibre_tag(node):
                flush_paragraph()
                continue
            text = node.get_text().strip()
            if text:
                flush_paragraph()
                new_body.append(node)
                new_body.append(NavigableString("\n"))
            continue

        if node.name in ("br", "h1", "h2", "h3", "h4", "h5", "h6", "div"):
            flush_paragraph()
            new_body.append(node)
            new_body.append(NavigableString("\n"))
            continue

        if node.name in ("b", "i", "span", "em", "strong", "a", "u", "sub", "sup"):
            if current_paragraph is None:
                current_paragraph = soup.new_tag("p")
            current_paragraph.append(node)
            continue

        flush_paragraph()
        new_body.append(node)
        new_body.append(NavigableString("\n"))

    flush_paragraph()

    new_text = set(new_body.get_text().strip().split())
    assert old_text == new_text, f"Text changed: old={old_text - new_text}, new={new_text - old_text}"
    old_body.replace_with(new_body)
    return soup.prettify()


def is_empty_calibre_tag_lxml(tag) -> bool:
    if tag.tag != "p":
        return False
    classes = tag.get("class", "").split()
    if not any("calibre" in str(c) for c in classes):
        return False
    text = (tag.text or "").strip()
    return not text or text == "\xa0"


def _get_text_content(elem) -> str:
    return "".join(elem.itertext())


def cleanup_calibre_formatting_lxml(content: bytes) -> bytes:
    doc = html.document_fromstring(content)
    body = require(doc.body)
    old_text = set(_get_text_content(body).strip().split())

    new_body = etree.Element("body")
    current_paragraph = None

    def flush_paragraph():
        nonlocal current_paragraph
        if current_paragraph is not None and (current_paragraph.text or len(current_paragraph) > 0):
            new_body.append(current_paragraph)
            new_body.tail = "\n"
            current_paragraph = None

    def add_text(text: str):
        nonlocal current_paragraph
        text = text.strip()
        if not text:
            return
        flush_paragraph()
        new_p = etree.Element("p")
        new_p.text = text
        new_body.append(new_p)
        new_body.tail = "\n"

    add_text(body.text if body.text else "")

    for node in list(body):
        if node.tag is etree.Entity:
            continue

        if node.tag == "p":
            text_inside = node.text if node.text else ""
            if is_empty_calibre_tag_lxml(node):
                flush_paragraph()
                if node.tail:
                    add_text(node.tail)
                node.tail = None
                continue
            if text_inside.strip():
                flush_paragraph()
                new_body.append(node)
                new_body.tail = "\n"
            if node.tail:
                add_text(node.tail)
                node.tail = None
            continue

        if node.tag in ("br", "h1", "h2", "h3", "h4", "h5", "h6", "div"):
            flush_paragraph()
            new_body.append(node)
            new_body.tail = "\n"
            if node.tail:
                add_text(node.tail)
                node.tail = None
            continue

        if node.tag in ("b", "i", "span", "em", "strong", "a", "u", "sub", "sup"):
            if current_paragraph is None:
                current_paragraph = etree.SubElement(new_body, "p")
            current_paragraph.append(node)
            if node.tail:
                add_text(node.tail)
                node.tail = None
            continue

        flush_paragraph()
        new_body.append(node)
        new_body.tail = "\n"
        if node.tail:
            add_text(node.tail)
            node.tail = None

    flush_paragraph()

    new_text = set(_get_text_content(new_body).strip().split())
    # assert old_text == new_text, f"Text changed: old={old_text - new_text}, new={new_text - old_text}"

    body.getparent().replace(body, new_body)
    return html.tostring(doc, pretty_print=True, encoding="utf-8")


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
