import logging
from pathlib import Path
from typing import Callable, Generator
from zipfile import ZipInfo

from lxml import html, etree
from lxml.html import HtmlElement
from lxml.etree import Element
from dataclasses import dataclass, field

from pydantic_xml import BaseXmlModel

from library.epub.epub_link import EPUBLinkType

from library.epub.media_type import MediaType, ResourceType, Category
from library.epub.utils_href import posix_absolute_href
from library.epub.xml_models.ncx_model import NavPoint
from library.epub.xml_models.package_sequences import ManifestItem, SpineItemRef, GuideReference
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file
from library.xml.utils import etree_from_bytes

logger = logging.getLogger("resource")


@dataclass
class EPUBLink:
    resource: EPUBResource
    filename: str = field(init=False)
    element: HtmlElement  # | BaseXmlModel
    link: str
    link_type: EPUBLinkType = field(init=False)
    absolute_path: str | None = field(default=None)

    def __post_init__(self):
        self.filename = self.resource.filename
        self.link_type = EPUBLinkType.from_link(self.link)
        if self.link_type == EPUBLinkType.RELATIVE_PATH:
            self.absolute_path = posix_absolute_href(self.filename, self.link)

    @classmethod
    def from_iterlinks(cls, resource: EPUBResource, link_data: tuple[HtmlElement, dict[str, str], str, int]):
        element, attribute, link, pos = link_data
        logger.info(f"link: {link!r}, pos: {pos!r}, attribute: {attribute!r}, element: {element!r}")
        return cls(resource=resource, element=element, link=link)

    @classmethod
    def from_etree_element(cls, resource: EPUBResource):
        pass


class EPUBResource:
    """Represents a single file in an EPUB archive."""

    def __init__(self, info: ZipInfo, read_bytes_func: Callable[[ZipInfo], bytes]) -> None:
        self.info: ZipInfo = info
        self._read_bytes_func = read_bytes_func

        self._content: bytes | None = None
        self._text: str | None = None
        self._html: HtmlElement | None = None
        self._xml_tree: Element | None = None

        self.media_type = MediaType.from_filename(info.filename)
        self.category = self.media_type.category
        self.resource_type = self.media_type.resource_type

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

    def _params(self) -> str:
        return f"({self.media_type!s}, {self.category!s}, {self.resource_type!s})"

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
            if self._xml_tree is not None:
                self.content = etree.tostring(self.xml_tree, pretty_print=True, xml_declaration=True, encoding="utf-8")
        if self._content is None:
            logger.debug(f"{self} reading content")
            self._content: bytes = self._read_bytes_func(self.original_info)
        assert self._content is not None, f"{self} could not read content"
        return self._content

    @content.setter
    def content(self, value: bytes) -> None:
        logger.info(f"{self} reassigning the byte contents")
        self._content = value

    @property
    def html(self) -> HtmlElement:
        if self.category is not Category.MARKUP_CONTENT:
            raise RuntimeError(f"{self} Invalid type for .html ({self._params()})")
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
    def xml_tree(self) -> Element:
        if not self.media_type.is_xml() and not self.is_nav_document():
            raise RuntimeError(f"{self} Invalid type for .xml_tree (({self._params()})")
        if self._xml_tree is None:
            self._xml_tree = etree_from_bytes(self.content)
        assert self._xml_tree is not None, f"{self} could not read content for xml_tree"
        return self._xml_tree

    @xml_tree.setter
    def xml_tree(self, value: Element) -> None:
        logger.info(f"{self} reassigning the xml_tree data")
        self._xml_tree = value
        # TODO: pretty_print, encoding via global env variable # encoding: Literal["unicode"] | None = None (for str)
        # self.content = etree.tostring(self.xml_tree, pretty_print=True, xml_declaration=True, encoding="utf-8")

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
        # TODO: setter
        if self.manifest_item:
            return self.manifest_item.id
        return None

    def is_spine_item(self) -> bool:
        return self.spine_item_ref is not None

    def is_nav_document(self) -> bool:
        return self.media_type is MediaType.XHTML and self.resource_type is ResourceType.CORE

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
        if self.category is not Category.MARKUP_CONTENT:
            raise RuntimeError(f"{self} Unknown type ({self.media_type!s}, {self.category!s}, {self.resource_type!s})")
        logger.debug(f"{self} parsing links")
        return [EPUBLink.from_iterlinks(self, link_data) for link_data in self.html.iterlinks()]


class ResourceIndex:
    """Auto-indexed collection of EPUBResource objects.

    Provides O(1) lookup by filename and by manifest ID,
    while maintaining a stable list for iteration.
    """

    def __init__(self, resources: list[EPUBResource] | None = None) -> None:
        self._items: list[EPUBResource] = []
        self._by_path: dict[str, EPUBResource] = {}
        self._by_id: dict[str, EPUBResource] = {}
        if resources:
            for r in resources:
                self.add(r)

    def __repr__(self) -> str:
        return f"ResourceIndex({len(self._items)})"

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, item: EPUBResource | str) -> bool:
        if isinstance(item, str):
            return item in self._by_path
        return item in self._items

    def add(self, resource: EPUBResource) -> None:
        """Add a resource to the index."""
        self._items.append(resource)
        self._by_path[resource.filename] = resource
        # TODO: add records of the resource to the documents
        if resource.id is not None:
            self._by_id[resource.id] = resource

    def remove(self, resource: EPUBResource) -> None:
        """Remove a resource from the index."""
        self._items.remove(resource)
        self._by_path.pop(resource.filename, None)
        # TODO: remove records of the resource from the documents
        if resource.id is not None:
            self._by_id.pop(resource.id)

    def by_path(self, path: str) -> EPUBResource | None:
        """Look up a resource by its filename/path."""
        return self._by_path.get(path)

    def by_id(self, _id: str) -> EPUBResource | None:
        """Look up a resource by its manifest ID."""
        return self._by_id.get(_id)

    def rebuild_id_index(self) -> None:
        """Rebuild the ID index (call after OPF enrichment populates IDs)."""
        logger.debug("rebuilding ID index")
        self._by_id = {r.id: r for r in self._items if r.id is not None}

    def core_items(self) -> Generator[EPUBResource, None, None]:
        for item in self._items:
            if item.resource_type is ResourceType.CORE:
                yield item

    def common_items(self) -> Generator[EPUBResource, None, None]:
        for item in self._items:
            if item.resource_type is ResourceType.COMMON:
                yield item

    def content_items(self) -> Generator[EPUBResource, None, None]:
        for item in self._items:
            if item.resource_type is ResourceType.CONTENT:
                yield item

    def unknown_items(self) -> Generator[EPUBResource, None, None]:
        for item in self._items:
            if item.resource_type is ResourceType.UNKNOWN:
                yield item

    def statistics(self) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        core = list(item.get_stats() for item in self.core_items())
        common = list(item.get_stats() for item in self.common_items())
        content = list(item.get_stats() for item in self.content_items())
        unknown = list(item.get_stats() for item in self.unknown_items())

        return core, common, content, unknown

    def interlink_resources(self):
        for item in self._items:
            if item.category is not Category.MARKUP_CONTENT:
                continue

            for epub_link in item.parse_links():
                item.linked_to.append(epub_link)
                if epub_link.absolute_path is not None:
                    linked_resource = self.by_path(epub_link.absolute_path)
                    assert linked_resource is not None, f"not found {epub_link.absolute_path}({epub_link.link})"
                    linked_resource.linked_by.append(epub_link)
