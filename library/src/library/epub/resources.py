import logging
from enum import Enum, auto
from typing import Callable
from zipfile import ZipInfo

from library.epub.media_type import MediaType, Category, ResourceType
from library.epub.xml_models.ncx_model import NavPoint
from library.epub.xml_models.package_sequences import ManifestItem, SpineItemRef, GuideReference

logger = logging.getLogger("resource")

class EPUBResource:
    """Represents a single file in an EPUB archive."""

    def __init__(self, info: ZipInfo, read_bytes_func: Callable[[str | ZipInfo], bytes]) -> None:
        self.info: ZipInfo = info
        self._content: bytes | None = None
        self._read_bytes_func = read_bytes_func

        self.media_type = MediaType.from_filename(info.filename)
        self.category = self.media_type.category
        self.resource_type = self.media_type.resource_type

        # OPF
        self.manifest_item: ManifestItem | None = None
        self.spine_item_ref: SpineItemRef | None = None
        self.guide_reference: GuideReference | None = None

        # NCX
        self.ncx_nav_point: NavPoint | None = None

    def __repr__(self) -> str:
        return f"EPUBResource({self.filename!r}, {self.media_type!s}, {self.category!s}, {self.resource_type!s})"

    @property
    def content(self) -> bytes:
        if self._content is None:
            self._content: bytes = self._read_bytes_func(self.info)
        assert self._content is not None, f"could not read content of {self.filename}"
        return self._content

    @content.setter
    def content(self, value: bytes) -> None:
        self._content = value

    @property
    def filename(self) -> str:
        return self.info.filename

    @filename.setter
    def filename(self, value: str) -> None:
        self.info.filename = value

    @property
    def is_spine_item(self) -> bool:
        return self.spine_item_ref is not None


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
        return f"ResourceIndex({len(self._items)} resources)"

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
            self._by_id.pop(resource.id, None)

    def by_path(self, path: str) -> EPUBResource | None:
        """Look up a resource by its filename/path."""
        return self._by_path.get(path)

    def by_id(self, _id: str) -> EPUBResource | None:
        """Look up a resource by its manifest ID."""
        return self._by_id.get(_id)

    def rebuild_id_index(self) -> None:
        """Rebuild the ID index (call after OPF enrichment populates IDs)."""
        logger.debug(f"rebuilding ID index")
        self._by_id = {r.id: r for r in self._items if r.id is not None}
