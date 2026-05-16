from dataclasses import dataclass, field
from urllib.parse import urlparse
from enum import StrEnum

from lxml.html import HtmlElement
from library.epub.utils_href import posix_absolute_href


class EPUBLinkType(StrEnum):
    RELATIVE_PATH = "RELATIVE_PATH"  # ../Images/fig1.jpg
    INTERNAL_ANCHOR = "INTERNAL_ANCHOR"  # #chapter1_ref (within same file)
    WEB_URL = "WEB_URL"  # https://example.com
    RELATIVE_PROTOCOL = "RELATIVE_PROTOCOL"  # //://example.com
    EMBEDDED_DATA = "EMBEDDED_DATA"  # data:image/png;base64...
    MAILTO = "MAILTO"  # mailto:author@example.com
    OTHER_SCHEME = "OTHER_SCHEME"  # tel:+123..., epub://, etc.

    @classmethod
    def from_link(cls, value: str) -> "EPUBLinkType":
        if not value:
            return cls.OTHER_SCHEME

        if value.startswith("//"):
            return cls.RELATIVE_PROTOCOL

        if value.startswith("#"):
            return cls.INTERNAL_ANCHOR

        parsed = urlparse(value)
        scheme = parsed.scheme.lower()
        if not scheme:
            return cls.RELATIVE_PATH

        if scheme in ("http", "https"):
            return cls.WEB_URL
        if scheme == "data":
            return cls.EMBEDDED_DATA
        if scheme == "mailto":
            return cls.MAILTO

        return cls.OTHER_SCHEME


@dataclass
class EPUBLink:
    filename: str
    element: HtmlElement  # | BaseXmlModel
    link: str
    link_type: EPUBLinkType = field(init=False)
    absolute_path: str | None = field(default=None)

    def __post_init__(self):
        self.link_type = EPUBLinkType.from_link(self.link)
        if self.link_type == EPUBLinkType.RELATIVE_PATH:
            self.absolute_path = posix_absolute_href(self.filename, self.link)

    @classmethod
    def from_iterlinks(cls, filename: str, link_data: tuple[HtmlElement, dict[str, str], str, int]):
        element, attribute, link, pos = link_data
        return cls(filename=filename, element=element, link=link)
