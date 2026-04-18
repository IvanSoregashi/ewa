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


def from_html_head_parse_links(head: HtmlElement) -> list:
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
    return stylesheets + other_links


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


def from_html_body_parse_attachments(body: HtmlElement, tag: str | None = None) -> list:

    images = []
    other_attachments = []

    for element, attribute, link, pos in body.iterlinks():
        logger.debug(f"{element.tag}, {attribute}, {link}")
        if link.startswith("#"):
            continue
        attrs = element.attrib
        tpl = (element.tag, attrs, element.text_content())
        if element.tag in ("img", "image", "picture", "source"):
            images.append(tpl)
            continue
        other_attachments.append(tpl)
    return images + other_attachments


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
