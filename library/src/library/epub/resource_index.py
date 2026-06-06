import logging
from collections.abc import Callable
from typing import Literal, overload, BinaryIO
from zipfile import ZipInfo

from library.epub.resources import RoleBasedResource, EpubImageResource
from library.epub.media_type import EpubRole, MediaType
from library.epub.resources import (
    EpubHtmlResource,
    EpubContainerResource,
    EpubPackageResource,
    EpubXmlResource,
    EpubDefaultResource,
    EpubNcxResource,
    get_resource_stats,
    PackagedResource,
    instantiate_resource,
)

logger = logging.getLogger("resource_index")

AnyResource = (
    EpubHtmlResource
    | EpubContainerResource
    | EpubPackageResource
    | EpubXmlResource
    | EpubDefaultResource
    | EpubNcxResource
)


class ResourceIndex:
    """Auto-indexed collection of EPUBResource objects.

    Provides O(1) lookup by filename and by manifest ID,
    while maintaining a stable list for iteration.
    """

    def __init__(self, infolist: list[ZipInfo], stream: Callable[[ZipInfo], BinaryIO]) -> None:
        self._items: list[AnyResource] = []
        self._by_path: dict[str, AnyResource] = {}
        self._by_id: dict[str, AnyResource] = {}
        if infolist:
            for info in infolist:
                resource = instantiate_resource(info=info, stream_bytes=stream)
                self.add(resource)

    def __repr__(self) -> str:
        return f"ResourceIndex({len(self._items)})"

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, item: EpubDefaultResource | str) -> bool:
        if isinstance(item, str):
            return item in self._by_path
        return item in self._items

    def add(self, resource) -> None:
        """Add a resource to the index."""
        self._items.append(resource)
        self._by_path[resource.info.filename] = resource
        # TODO: add records of the resource to the documents
        if getattr(resource, "id", None):
            self._by_id[resource.id] = resource

    def remove(self, resource: EpubDefaultResource) -> None:
        """Remove a resource from the index."""
        self._items.remove(resource)
        self._by_path.pop(resource.info.filename, None)
        if resource.id is not None:
            self._by_id.pop(resource.id)

    def by_path(self, path: str) -> AnyResource | None:
        """Look up a resource by its filename/path."""
        return self._by_path.get(path)

    def by_path_as[T: RoleBasedResource](self, path: str, expected_type: type[T]) -> T | None:
        res = self.by_path(path)
        if isinstance(res, expected_type):
            return res
        else:
            logger.error(f"{self} type for {path!r}({type(path)!r}) differs from expected {expected_type.__name__}")
        return None

    def by_id(self, _id: str) -> AnyResource | None:
        """Look up a resource by its manifest ID."""
        return self._by_id.get(_id)

    def all_by_media(self, media: MediaType) -> list[AnyResource]:
        return [r for r in self._items if r.media_type == media]

    @overload
    def all_by_role(self, role: Literal[EpubRole.HTML]) -> list[EpubHtmlResource]: ...
    @overload
    def all_by_role(self, role: Literal[EpubRole.XML]) -> list[EpubXmlResource]: ...
    @overload
    def all_by_role(self, role: Literal[EpubRole.IMAGE]) -> list[EpubImageResource]: ...
    @overload
    def all_by_role(self, role: EpubRole) -> list[EpubDefaultResource]: ...

    def all_by_role(self, role: EpubRole) -> list:
        return [r for r in self._items if r.role == role]

    def rebuild_id_index(self) -> None:
        """Rebuild the ID index (call after OPF enrichment populates IDs)."""
        self._by_id = {r.id: r for r in self._items if r.id is not None}

    @property
    def styles(self) -> list[EpubDefaultResource]:
        """All CSS stylesheets in the EPUB."""
        return self.all_by_role(EpubRole.STYLE)

    @property
    def fonts(self) -> list[EpubDefaultResource]:
        """All font files in the EPUB."""
        return self.all_by_role(EpubRole.FONT)

    @property
    def images(self) -> list[EpubImageResource]:
        """All image files in the EPUB."""
        return self.all_by_role(EpubRole.IMAGE)

    @property
    def markup_content(self) -> list[EpubHtmlResource]:
        return self.all_by_role(EpubRole.HTML)

    def core_items(self):
        return [r for r in self._items if r.role.is_core()]

    def common_items(self):
        return [r for r in self._items if r.role.is_common()]

    def statistics(self) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        core = [get_resource_stats(r) for r in self._items if r.role.is_core()]
        common = [get_resource_stats(r) for r in self._items if r.role.is_common()]
        content = [get_resource_stats(r) for r in self._items if r.role.is_content()]
        unknown = [get_resource_stats(r) for r in self._items if r.role.is_other()]

        return core, common, content, unknown

    def interlink_resources(self):
        for item in self.all_by_role(EpubRole.HTML):
            for epub_link in item.parse_links():
                item.linked_to.append(epub_link)
                if epub_link.absolute_path is not None:
                    linked_resource = self.by_path(epub_link.absolute_path)
                    assert linked_resource is not None, f"not found {epub_link.absolute_path}({epub_link.link})"
                    assert isinstance(linked_resource, PackagedResource), (
                        f"Resource {epub_link.absolute_path} is not a packaged resource"
                    )
                    linked_resource.linked_by.append(epub_link)
