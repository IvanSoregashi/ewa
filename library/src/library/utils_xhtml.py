from lxml import html
from lxml.html import HtmlElement
import json
import logging

logger = logging.getLogger(__file__)


def from_html_head_parse_frontmatter(head: HtmlElement) -> dict:
    metadata_scripts = head.xpath('.//script[@id="frontmatter" and @type="application/ld+json"]')
    if metadata_scripts and metadata_scripts[0].text_content():
        return json.loads(metadata_scripts[0].text_content())
    return {}


def from_html_head_parse_links(head: HtmlElement) -> dict[str, HtmlElement]:
    stylesheets = {}
    for element, attribute, link, pos in head.iterlinks():
        attrs = element.attrib
        if attrs.get("rel") == "stylesheet" and attrs.get("type") == "text/css":
            stylesheets[link] = element
            continue
        logger.warning(f"found non-style attachment {element.tag, attrs, element.text_content()}, discarding")
    return stylesheets


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


def from_html_body_parse_attachments(body: HtmlElement, tag: str | None = None) -> dict[str, HtmlElement]:
    images = {}
    tags = (tag,) or ("img", "image", "picture", "source")
    for element, attribute, link, pos in body.iterlinks():
        if link.startswith("#"):
            logger.warning(f"unknown link {attribute} {link}")
            continue
        if element.tag in tags:
            images[link] = element
            continue
        logger.info(f"found non-image attachment {element.tag, element.attrib, element.text_content()}, discarding")
    return images


def parse_html_content(file_content: str | bytes) -> tuple[dict, list, list]:
    """ """
    tree: HtmlElement = html.document_fromstring(file_content)

    head: HtmlElement = tree.find(".//head")
    title = head.xpath(".//title")[0].text_content()
    metadata: dict = from_html_head_parse_frontmatter(head)
    head_attach = from_html_head_parse_links(head)

    body: HtmlElement = tree.find(".//body")

    if not metadata:
        first_header = from_html_body_parse_first_header(body)
        highest_header = from_html_body_parse_highest_header(body)
        logger.debug(f"{first_header=}")
        logger.debug(f"{highest_header=}")
        metadata["title"] = first_header

    body_attach = from_html_body_parse_attachments(body)

    return metadata, head_attach, body_attach


def parse_html_attachments(file_content: str | bytes) -> tuple[list, list]:
    """ """
    tree: HtmlElement = html.document_fromstring(file_content)
    head: HtmlElement = tree.find(".//head")
    head_attachments = from_html_head_parse_links(head)
    body: HtmlElement = tree.find(".//body")
    body_attachments = from_html_body_parse_attachments(body)
    return head_attachments, body_attachments


def parse_stylesheets_and_images(tree: HtmlElement) -> tuple[dict[str, HtmlElement], dict[str, HtmlElement]]:
    stylesheets = from_html_head_parse_links(tree.find(".//head"))
    images = from_html_head_parse_links(tree.find(".//body"))
    return stylesheets, images


def parse_links(tree: HtmlElement) -> dict[str, HtmlElement]:
    attachments = {}
    for element, attribute, link, pos in tree.iterlinks():
        attachments[link] = element
    return attachments
