import logging
from pathlib import Path
from typing import Callable
from zipfile import ZipInfo

from lxml import html, etree
from lxml.html import HtmlElement
from lxml.etree import Element
from hashlib import md5


from epub.utils import SQLITE_MAX_INT
from library.epub.epub_link import EPUBLink

from library.epub.media_type import type_and_role_from_filename, EpubRole
from library.epub.xml_models.ncx_model import NavPoint
from library.epub.xml_models.package_sequences import ManifestItem, SpineItemRef, GuideReference
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file
from library.xml.utils import etree_from_bytes

logger = logging.getLogger("resource")


class EPUBResource:
    """Represents a single file in an EPUB archive."""

    def __init__(self, info: ZipInfo, read_bytes_func: Callable[[ZipInfo], bytes]) -> None:
        self.info: ZipInfo = info
        self._read_bytes_func = read_bytes_func

        self._content: bytes | None = None
        self._hex_hash: str | None = None
        self._text: str | None = None
        self._html: HtmlElement | None = None
        self._xml: Element | None = None

        self.media_type, self.role = type_and_role_from_filename(info.filename)

        self.is_modified = False
        self.is_deleted = False
        self.linked_to: list[EPUBLink] = list()
        self.linked_by: list[EPUBLink] = list()

        # OPF
        self.manifest_item: ManifestItem | None = None
        self.spine_item_ref: SpineItemRef | None = None
        self.guide_reference: GuideReference | None = None
        self.source_sequence: int | None = None

        # NCX
        self.ncx_nav_point: NavPoint | None = None

        # NAV
        self.navs: dict[str, NavPoint] = {}

    def __repr__(self) -> str:
        return f"EPUBResource({self.filename!r})"

    def __params__(self) -> str:
        return f"({self.media_type.value!r}, {self.role.value!r})"

    @classmethod
    def from_filesystem_path(cls, path: Path) -> EPUBResource:
        if not path.exists():
            raise ValueError(f"{path} does not exist, cannot create EPUBResource")
        info = ZipInfo.from_file(path, arcname=path.name, strict_timestamps=False)
        return cls(info=info, read_bytes_func=lambda i: Path(i.filename).read_bytes())

    @property
    def content(self) -> bytes:
        if self.is_modified:
            if self._html is not None:
                self.content = html.tostring(self.html, pretty_print=True)
            if self._xml is not None:
                self.content = etree.tostring(self.xml, pretty_print=True, xml_declaration=True, encoding="utf-8")
        if self._content is None:
            logger.debug(f"{self} reading content")
            self._content: bytes = self._read_bytes_func(self.info)
        assert self._content is not None, f"{self} could not read content"
        return self._content

    @content.setter
    def content(self, value: bytes) -> None:
        logger.info(f"{self} reassigning the byte contents")
        self._content = value

    @property
    def hex_hash(self):
        if self._hex_hash is None:
            self._hex_hash = md5(self.content).hexdigest()
        assert self._hex_hash is not None
        return self._hex_hash

    @property
    def int64_hash(self):
        return int(self.hex_hash, 16) % SQLITE_MAX_INT

    @property
    def html(self) -> HtmlElement:
        if not self.role.is_html():
            raise RuntimeError(f"{self} Invalid type for .html ({self.__params__()})")
        if self._html is None:
            self._html = html.document_fromstring(self.content)
        assert self._html is not None, f"{self} could not read content for html"
        return self._html

    @html.setter
    def html(self, value: HtmlElement) -> None:
        logger.info(f"{self} reassigning the html data")
        self._html = value
        # TODO: pretty_print, encoding via global env variable # encoding: Literal["unicode"] | None = None (for str)
        # self.content = html.tostring(value, pretty_print=True)

    @property
    def xml(self) -> Element:
        if not self.media_type.is_xml() and not self.is_nav_document():
            raise RuntimeError(f"{self} Invalid type for .xml ({self.__params__()})")
        if self._xml is None:
            self._xml = etree_from_bytes(self.content)
        assert self._xml is not None, f"{self} could not read content for xml"
        return self._xml

    @xml.setter
    def xml(self, value: Element) -> None:
        logger.info(f"{self} reassigning the xml data")
        self._xml = value
        # TODO: pretty_print, encoding via global env variable # encoding: Literal["unicode"] | None = None (for str)
        # self.content = etree.tostring(self.xml, pretty_print=True, xml_declaration=True, encoding="utf-8")

    @property
    def filename(self) -> str:
        return self.info.filename

    @filename.setter
    def filename(self, value: str) -> None:
        self.info.filename = value

    @property
    def null_info(self) -> ZipInfo:
        info = self.info
        info.CRC = 0
        info.file_size = 0
        info.compress_size = 0
        return info

    @property
    def hash_prefixed_name(self):
        return f"{self.int64_hash}_{Path(self.filename).name}"

    def write_to_filesystem(self, path: Path) -> EPUBResource:
        if path.exists():
            logger.warning(f"{self}, file {path} exists, nothing to write.")
        else:
            byte_count = path.write_bytes(self.content)
            apply_zipinfo_timestamp_to_file(self.info, path)
            logger.info(f"{self}, written {byte_count} bytes to {path}.")
        return EPUBResource.from_filesystem_path(path)

    @property
    def id(self) -> str | None:
        # TODO: setter?
        if self.manifest_item:
            return self.manifest_item.id
        return None

    def is_spine_item(self) -> bool:
        return self.spine_item_ref is not None

    def is_nav_document(self) -> bool:
        return self.role is EpubRole.NAV

    def get_stats(self) -> dict:
        return {
            "filename": self.info.filename,
            "media_type": self.media_type,
            "manifest_media_type": self.manifest_item and self.manifest_item.media_type,
            "id": self.manifest_item and self.manifest_item.id,
            "spine": bool(self.spine_item_ref),
            "links_to": len(self.linked_to),
            "links_by": len(self.linked_by),
            "guide": bool(self.guide_reference),
            "ncx_label": self.ncx_nav_point and self.ncx_nav_point.nav_label.text,
            "nav": bool(self.navs),
        }

    def parse_links(self) -> list[EPUBLink]:
        if self.role is not EpubRole.HTML:
            raise RuntimeError(f"{self} Unknown type  ({self.__params__()})")
        logger.debug(f"{self} parsing links")
        return [EPUBLink.from_iterlinks(self.filename, link_data) for link_data in self.html.iterlinks()]
