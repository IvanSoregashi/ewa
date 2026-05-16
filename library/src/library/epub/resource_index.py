from typing import Literal, overload

from library.epub.media_type import EpubRole, MediaType
from library.epub.resources import EPUBResource


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

    def by_media(self, media: MediaType) -> list[EPUBResource]:
        return [r for r in self._items if r.media_type == media]

    @overload
    def by_role(self, role: Literal[EpubRole.HTML]) -> list[EPUBResource]: ...
    @overload
    def by_role(self, role: Literal[EpubRole.XML]) -> list[EPUBResource]: ...

    def by_role(self, role: EpubRole) -> list[EPUBResource]:
        return [r for r in self._items if r.role == role]

    def rebuild_id_index(self) -> None:
        """Rebuild the ID index (call after OPF enrichment populates IDs)."""
        self._by_id = {r.id: r for r in self._items if r.id is not None}

    @property
    def styles(self) -> list[EPUBResource]:
        """All CSS stylesheets in the EPUB."""
        return self.by_role(EpubRole.STYLE)

    @property
    def fonts(self) -> list[EPUBResource]:
        """All font files in the EPUB."""
        return self.by_role(EpubRole.FONT)

    @property
    def images(self) -> list[EPUBResource]:
        """All image files in the EPUB."""
        return self.by_role(EpubRole.IMAGE)

    @property
    def markup_content(self) -> list[EPUBResource]:
        return self.by_role(EpubRole.HTML)

    def core_items(self):
        return [r for r in self._items if r.role.is_core()]

    def common_items(self):
        return [r for r in self._items if r.role.is_common()]

    def statistics(self) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        core = [r.get_stats() for r in self._items if r.role.is_core()]
        common = [r.get_stats() for r in self._items if r.role.is_common()]
        content = [r.get_stats() for r in self._items if r.role.is_content()]
        unknown = [r.get_stats() for r in self._items if r.role.is_other()]

        return core, common, content, unknown

    def interlink_resources(self):
        for item in self.by_role(EpubRole.HTML):
            for epub_link in item.parse_links():
                item.linked_to.append(epub_link)
                if epub_link.absolute_path is not None:
                    linked_resource = self.by_path(epub_link.absolute_path)
                    assert linked_resource is not None, f"not found {epub_link.absolute_path}({epub_link.link})"
                    linked_resource.linked_by.append(epub_link)
