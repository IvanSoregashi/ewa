from dataclasses import dataclass

from lxml import etree
from lxml.html import HtmlElement, document_fromstring

from library.epub.resources import Resource
from library.epub.utils_href import posix_absolute_href, posix_relative_href

_xml_parser = etree.XMLParser(huge_tree=True)
_xml_parser.set_element_class_lookup(etree.ElementDefaultClassLookup(element=HtmlElement))


@dataclass
class VideoTagInfo:
    """Replacement data for one converted animation (oversized GIF -> MP4 + poster).

    The poster shares the basename with the mp4, so both derive from a single
    replacement-mechanism entry (old gif archive path -> VideoTagInfo)."""

    video_path: str  # archive path of the mp4
    poster_path: str  # archive path of the poster jpeg
    width: int
    height: int
    alt: str = ""


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


def _video_element(img: HtmlElement, info: VideoTagInfo, document_path: str) -> HtmlElement:
    """Build the device-validated video tag (Moon+/BOOX) in the img's namespace:
    src + poster + controls + preload, with <source> and <img> children."""
    namespace = etree.QName(img).namespace
    ns = f"{{{namespace}}}" if namespace else ""
    video = etree.Element(f"{ns}video")
    video.set("src", posix_relative_href(document_path, info.video_path))
    video.set("poster", posix_relative_href(document_path, info.poster_path))
    video.set("controls", "controls")
    video.set("preload", "metadata")
    video.set("width", str(info.width))
    video.set("height", str(info.height))
    video.set("style", "max-width:100%")
    source = etree.SubElement(video, f"{ns}source")
    source.set("src", video.get("src"))
    source.set("type", "video/mp4")
    poster = etree.SubElement(video, f"{ns}img")
    poster.set("src", video.get("poster"))
    poster.set("alt", info.alt)
    return video


def replace_gifs_with_videos(
    resource: Resource, table: dict[str, VideoTagInfo], pretty_print_result: bool = False
) -> int:
    """Replace <img> elements pointing at converted animations with video tags.

    The table maps ARCHIVE paths of the original gifs (old -> VideoTagInfo);
    document links are resolved relative to the document's own location, same
    as replace_links. Output stays valid parseable XML.

    Returns the number of replaced images.
    """
    try:
        html: HtmlElement = etree.fromstring(resource.content, _xml_parser)
    except etree.XMLSyntaxError:
        html = document_fromstring(resource.content)

    replacements = []
    for element, attribute, link, pos in html.iterlinks():
        if attribute != "src" or not isinstance(element.tag, str) or etree.QName(element).localname != "img":
            continue
        info = table.get(posix_absolute_href(resource.filename, link))
        if info is not None:
            replacements.append((element, info))

    for element, info in replacements:
        element.getparent().replace(element, _video_element(element, info, resource.filename))

    resource.content = etree.tostring(
        html.getroottree(),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=pretty_print_result,
    )
    return len(replacements)
