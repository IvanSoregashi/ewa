import io
import logging
from contextlib import AbstractContextManager, contextmanager
from collections.abc import Iterable, Sequence
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, IO, Generator, Self
from zipfile import ZipInfo

from hashlib import md5

from library.asserts import require
from library.database.constants import SQLITE_MAX_INT

from library.epub.media_type import type_and_role_from_filename, EpubRole, MediaType
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file, zip_info_now

logger = logging.getLogger("resource")


class Resource:
    def __init__(
        self,
        info: ZipInfo,
        *,
        content: bytes | None = None,
        stream_bytes: Callable[[ZipInfo], AbstractContextManager[IO[bytes]]] | None = None,
    ) -> None:
        """Create a resource from bytes, without a backing source."""
        self.info = copy(info)
        self._source_info: ZipInfo = copy(info)
        assert content is not None or stream_bytes is not None, f"{self} content or streaming function must be provided"
        self._content: bytes | None = content
        self.stream_bytes = stream_bytes

        self.media_type, self.role = type_and_role_from_filename(self.info.filename)
        # logger.debug(f"{self} MediaType({self.media_type}) EpubRole({self.role})")

        self._hex_hash: str | None = None

    def __repr__(self) -> str:
        return f"Resource({self.info.filename!r})"

    @classmethod
    def from_bytes(cls, filename: str, content: bytes) -> Self:
        info = ZipInfo(filename, date_time=zip_info_now())
        info.file_size = len(content)
        return cls(info, content=content)

    @classmethod
    def from_filesystem_path(cls, path: Path) -> Self:
        if not path.exists():
            raise ValueError(f"{path} does not exist, cannot create LazyLoadFile")
        path = path.absolute()
        info = ZipInfo.from_file(path, strict_timestamps=False)
        return cls(info=info, stream_bytes=lambda i: path.open("rb"))

    def write_to_filesystem(self, path: Path) -> Resource:
        if path.exists():
            logger.warning(f"{self} writing to {str(path)!s}, aborting the write, returning the existing file.")
        else:
            byte_count = path.write_bytes(self.content)
            apply_zipinfo_timestamp_to_file(self.info, path)
            logger.debug(f"{self}, written {byte_count} bytes to {path}.")
        return self.__class__.from_filesystem_path(path)

    @contextmanager
    def stream(self) -> Generator[IO[bytes], None, None]:
        stream_func = require(self.stream_bytes, "stream_bytes")
        streamable = io.BytesIO(self._content) if self._content is not None else stream_func(self._source_info)
        with streamable as stream:
            yield stream

    @property
    def content(self) -> bytes:
        if self._content is None:
            with self.stream() as stream:
                self._content = stream.read()
        return require(self._content, "_content")

    @content.setter
    def content(self, value: bytes) -> None:
        # logger.debug(f"{self} reassigning the byte contents")
        self._content = value

    @property
    def hex_hash(self) -> str:
        if self._hex_hash is None:
            self._hex_hash = md5(self.content).hexdigest()
        assert self._hex_hash is not None
        return self._hex_hash

    @property
    def int64_hash(self):
        return int(self.hex_hash, 16) % SQLITE_MAX_INT

    @property
    def hash_prefixed_name(self):
        return f"{self.int64_hash}_{Path(self.info.filename).name}"

    @property
    def filename(self):
        return self.info.filename

    @filename.setter
    def filename(self, value: str) -> None:
        self.info.filename = value
        self.media_type, self.role = type_and_role_from_filename(self.info.filename)


class ResourceSelection(Sequence[Resource]):
    """Read-only membership snapshot; the resources themselves remain editable.

    Removal from an owning index does not rewrite previously taken snapshots.
    Export the owner's current inventory, not an old selection, to reflect removals.
    """

    def __init__(self, resources: Iterable[Resource]) -> None:
        self._items: Sequence[Resource] = tuple(resources)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self)})"

    @property
    def items(self) -> tuple[Resource, ...]:
        return tuple(self._items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, item):
        return self._items[item]

    def __contains__(self, item: object) -> bool:
        return self.by_path(item) is not None if isinstance(item, str) else item in self._items

    def by_path(self, path: str) -> Resource | None:
        return next((r for r in self._items if r.filename == path), None)

    def by_media_type(self, media_type: MediaType) -> ResourceSelection:
        return ResourceSelection(r for r in self if r.media_type == media_type)

    def by_role(self, role: EpubRole) -> ResourceSelection:
        return ResourceSelection(r for r in self if r.role == role)

    def iter(self, sort_by_role: bool = True) -> Generator[Resource, None, None]:
        if sort_by_role:
            for role in EpubRole:
                yield from (r for r in self if r.role == role)
        else:
            yield from self

    def stats(self):
        return IndexInfo(
            count=len(self),
            total_size=sum(i.info.file_size for i in self),
            compress_size=sum(i.info.compress_size for i in self),
        )


class ResourceIndex(ResourceSelection):
    """Owning resource inventory with unique paths and O(1) path lookup."""

    def __init__(self) -> None:
        self._items: list[Resource] = []
        self._by_path: dict[str, Resource] = {}

    @classmethod
    def from_infolist(
        cls, infolist: list[ZipInfo], stream: Callable[[ZipInfo], AbstractContextManager[IO[bytes]]]
    ) -> ResourceIndex:
        return cls.from_resource_list([Resource(info=info, stream_bytes=stream) for info in infolist])

    @classmethod
    def from_resource_list(cls, resource_list: list[Resource]) -> ResourceIndex:
        result = cls()
        for resource in resource_list:
            result.add(resource)
        return result

    def add(self, resource: Resource) -> None:
        if resource.filename in self._by_path or resource in self._items:
            raise ValueError(f"Resource already indexed: {resource.filename!r}")
        self._items.append(resource)
        self._by_path[resource.filename] = resource

    def rename(self, resource: Resource, new_filename: str) -> None:
        """Rename an owned resource and its lookup; does not rewrite document links."""
        old_filename = resource.filename
        if resource not in self._items or self._by_path.get(old_filename) is not resource:
            raise ValueError("Resource is not indexed under its current filename")
        if not new_filename:
            raise ValueError("Resource filename must not be empty")
        if new_filename == old_filename:
            return
        if new_filename in self._by_path:
            raise ValueError(f"Resource already exists at {new_filename!r}")
        resource.filename = new_filename
        del self._by_path[old_filename]
        self._by_path[new_filename] = resource

    def remove(self, resource: Resource) -> None:
        """Remove membership only. Package.remove_resource coordinates OPF changes."""
        if resource not in self._items or self._by_path.get(resource.filename) is not resource:
            raise ValueError("Resource is not indexed under its current filename")
        self._items.remove(resource)
        del self._by_path[resource.filename]

    def by_path(self, path: str) -> Resource | None:
        return self._by_path.get(path)


@dataclass
class IndexInfo:
    count: int
    total_size: int
    compress_size: int
