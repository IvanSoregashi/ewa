import logging
from typing import Callable, Generator
from zipfile import ZipInfo

from lxml import html
from lxml.html import HtmlElement
from pygments.lexers import resource

from library.epub.media_type import MediaType, ResourceType, Category
from library.epub.utils_path import get_relative_href, get_absolute_href, posix_absolute_href, posix_relative_href
from library.epub.xml_models.ncx_model import NavPoint
from library.epub.xml_models.package_sequences import ManifestItem, SpineItemRef, GuideReference
from library.utils_xhtml import parse_html_attachments

logger = logging.getLogger("resource")


class EPUBResource:
    """Represents a single file in an EPUB archive."""

    def __init__(self, info: ZipInfo, read_bytes_func: Callable[[str | ZipInfo], bytes]) -> None:
        self.info: ZipInfo = info
        self._content: bytes | None = None
        self._html: HtmlElement | None = None
        self._read_bytes_func = read_bytes_func

        self.media_type = MediaType.from_filename(info.filename)
        self.category = self.media_type.category
        self.resource_type = self.media_type.resource_type

        self.stylesheets = dict()
        self.illustrations = dict()

        # OPF
        self.manifest_item: ManifestItem | None = None
        self.source_sequence: int | None = None
        self.spine_item_ref: SpineItemRef | None = None
        self.guide_reference: GuideReference | None = None

        # NCX
        self.ncx_nav_point: NavPoint | None = None

        # NAV
        self.navs: dict[str, NavPoint] = {}

        logger.debug(f"{self} stats loaded ({self.media_type!s}, {self.category!s}, {self.resource_type!s})")

    def __repr__(self) -> str:
        return f"EPUBResource({self.filename!r})"

    @property
    def content(self) -> bytes:
        if self._content is None:
            logger.debug(f"{self} reading content")
            self._content: bytes = self._read_bytes_func(self.info)
        assert self._content is not None, f"{self} could not read content"
        return self._content

    @content.setter
    def content(self, value: bytes) -> None:
        self._content = value

    @property
    def html(self) -> HtmlElement:
        if self.category is Category.MARKUP_CONTENT:
            raise RuntimeError(f"{self} Unknown type ({self.media_type!s}, {self.category!s}, {self.resource_type!s})")
        if self._html is None:
            self._html = html.document_fromstring(self.content)
        assert self._html is not None, f"{self} could not read content"
        return self._html

    @html.setter
    def html(self, value: HtmlElement) -> None:
        self._html = value

    @property
    def filename(self) -> str:
        return self.info.filename

    @filename.setter
    def filename(self, value: str) -> None:
        self.info.filename = value

    @property
    def is_spine_item(self) -> bool:
        return self.spine_item_ref is not None

    @property
    def id(self) -> str | None:
        if self.manifest_item:
            return self.manifest_item.id
        return None

    def get_stats(self) -> dict:
        return {
            "filename": self.info.filename,
            "media_type": self.media_type,
            "manifest_media_type": self.manifest_item and self.manifest_item.media_type,
            "id": self.manifest_item and self.manifest_item.id,
            "spine": bool(self.spine_item_ref),
            "styles": len(self.stylesheets),
            "images": len(self.illustrations),
            "guide": bool(self.guide_reference),
            "ncx_label": self.ncx_nav_point and self.ncx_nav_point.nav_label.text,
            "nav": bool(self.navs),
        }

    def parse_linked_resources(self) -> None:
        if self.category is Category.MARKUP_CONTENT:
            head_links, body_links = parse_html_attachments(self.content)
            self.stylesheets = {
                relative_link: posix_absolute_href(self.filename, relative_link) for relative_link in head_links
            }
            self.illustrations = {
                relative_link: posix_absolute_href(self.filename, relative_link) for relative_link in body_links
            }
            return None
        raise RuntimeError(f"{self} Unknown type ({self.media_type!s}, {self.category!s}, {self.resource_type!s})")


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
            item.parse_linked_resources()
