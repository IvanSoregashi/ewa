from lxml import html
from lxml.html import HtmlElement
import json
import logging
import markdownify
import markdown_it

logger = logging.getLogger("parsing_html")

def from_html_head_parse_frontmatter(head: HtmlElement) -> dict:
    metadata_scripts = head.xpath('.//script[@id="frontmatter" and @type="application/ld+json"]')
    if metadata_scripts and metadata_scripts[0].text_content():
        return json.loads(metadata_scripts[0].text_content())
    return {}

def from_html_head_parse_links(head: HtmlElement) -> tuple[list, list]:
    stylesheets = []
    other_links = []
    for element, attribute, link, pos in head.iterlinks():
        logger.debug(f"{element.tag}, {attribute}, {link}")
        attrs = element.attrib
        tpl = (element.tag, attrs, element.text_content())
        if attrs.get("rel") == "stylesheet" and attrs.get("type") == "text/css":
            stylesheets.append(tpl)
            continue
        other_links.append(tpl)
    return stylesheets, other_links

def from_html_body_parse_first_header(body: HtmlElement) -> str | None:
    header = body.xpath('.//h1|.//h2|.//h3|.//h4|.//h5|.//h6')
    if header:
        return header[0].text_content()
    return None

def from_html_body_parse_highest_header(body: HtmlElement) -> str | None:
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        found = body.find(f".//{tag}")
        if found is not None:
            return found.text_content()
    return None

def from_html_body_parse_attachments(body: HtmlElement, tag: str | None = None):

    images = []
    other_attachments = []

    for element, attribute, link, pos in body.iterlinks():
        logger.debug(f"{element.tag}, {attribute}, {link}")
        if link.startswith('#'):
            continue
        if element.tag in ("img", "image", "picture", "source"):
            images.append((link, element.attrib.get("alt") or element.text_content()))
            continue
        other_attachments.append(element.tag, element.attrib)
    return images, other_attachments


def parse_html_content(file_content: str | bytes) -> dict:
    """

    """
    tree: HtmlElement = html.document_fromstring(file_content)

    head: HtmlElement = tree.find('.//head')
    metadata: dict = from_html_head_parse_frontmatter(head)
    stylesheets, other_links = from_html_head_parse_links(head)

    body: HtmlElement = tree.find(".//body")

    if not metadata:
        first_header = from_html_body_parse_first_header(body)
        highest_header = from_html_body_parse_highest_header(body)
        logger.debug(f"{first_header=}")
        logger.debug(f"{highest_header=}")
        metadata["title"] = first_header

    images, other_attachments = from_html_body_parse_attachments(body)

    return metadata, images
