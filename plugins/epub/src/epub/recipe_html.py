"""Device-specific markup for replacing converted GIFs with video and poster tags.

General text and link editing lives in library.epub.html_editing.
"""

from dataclasses import dataclass
from lxml import etree
from lxml.html import document_fromstring
from library.epub.resources import Resource
from library.epub.utils_href import posix_absolute_href, posix_relative_href

_xml_parser = etree.XMLParser(huge_tree=True)
_LINK_XPATH = etree.XPath("//@*[local-name() = 'src']")


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


def _video_element(img: etree._Element, info: VideoTagInfo, document_path: str) -> etree._Element:
    """Build the device-validated video tag (Moon+/BOOX) in the img's namespace:
    src + poster + controls + preload, with <source> and <img> children."""
    namespace = etree.QName(img).namespace
    ns = f"{{{namespace}}}" if namespace else ""
    video = etree.Element(f"{ns}video")
    video_href = posix_relative_href(document_path, info.video_path)
    poster_href = posix_relative_href(document_path, info.poster_path)
    video.set("src", video_href)
    video.set("poster", poster_href)
    video.set("controls", "controls")
    video.set("preload", "metadata")
    video.set("width", str(info.width))
    video.set("height", str(info.height))
    video.set("style", "max-width:100%")
    source = etree.SubElement(video, f"{ns}source")
    source.set("src", video_href)
    source.set("type", "video/mp4")
    poster = etree.SubElement(video, f"{ns}img")
    poster.set("src", poster_href)
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
        html: etree._Element = etree.fromstring(resource.content, _xml_parser)
    except etree.XMLSyntaxError:
        html = document_fromstring(resource.content)

    replacements = []
    for item in _LINK_XPATH(html):
        if item.attrname != "src":
            continue
        element = item.getparent()
        if not isinstance(element.tag, str) or etree.QName(element).localname != "img":
            continue
        info = table.get(posix_absolute_href(resource.filename, str(item)))
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
