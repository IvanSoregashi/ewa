import io
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable, BinaryIO, Generator
from zipfile import ZipInfo

from lxml import html, etree
from lxml.html import HtmlElement
from lxml.etree import Element
from hashlib import md5
from PIL import Image

from library.asserts import require
from library.database.constants import SQLITE_MAX_INT
from library.epub.epub_link import EPUBLink

from library.epub.media_type import type_and_role_from_filename, EpubRole, MediaType
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.nav_model import NavDocument
from library.epub.xml_models.ncx_model import NavPoint, NCXDocument
from library.epub.xml_models.package_document import PackageDocument
from library.epub.xml_models.package_sequences import ManifestItem, SpineItemRef, GuideReference
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file
from library.image.models import ImageInfo
from library.image.optimization import optimization_machine, get_image_header_info, get_image_transparency_info
from library.utils_xhtml import pretty_print
from library.xml.document_pydantic import XMLDocumentModel
from library.xml.utils import etree_from_bytes

logger = logging.getLogger("resource")


class Resource:
    def __init__(self, info: ZipInfo, stream_bytes: Callable[[ZipInfo], BinaryIO]) -> None:
        self.info = info
        self.stream_bytes = stream_bytes

        self.media_type, self.role = type_and_role_from_filename(self.info.filename)
        logger.debug(f"{self} MediaType({self.media_type}) EpubRole({self.role})")

        self.is_modified: bool = False
        self.is_deleted: bool = False

        self._content: bytes | None = None
        self._hex_hash: str | None = None

    def __repr__(self) -> str:
        return f"Resource({self.info.filename!r})"

    @classmethod
    def from_filesystem_path(cls, path: Path):
        if not path.exists():
            raise ValueError(f"{path} does not exist, cannot create LazyLoadFile")
        info = ZipInfo.from_file(path, strict_timestamps=False)
        return cls(info=info, stream_bytes=lambda i: Path(i.filename).open("rb"))

    def write_to_filesystem(self, path: Path) -> Resource:
        if path.exists():
            logger.warning(f"{self} writing to {str(path)!s}, aborting the write, returning the existing file.")
        else:
            byte_count = path.write_bytes(self.content)
            apply_zipinfo_timestamp_to_file(self.info, path)
            logger.debug(f"{self}, written {byte_count} bytes to {path}.")
        return self.__class__.from_filesystem_path(path)

    @contextmanager
    def stream(self) -> Generator[BinaryIO, None, None]:
        if self._content is not None:
            streamable = io.BytesIO(self._content)
            yield streamable
        else:
            with self.stream_bytes(self.info) as stream:
                yield stream

    @property
    def content(self) -> bytes:
        if self._content is None:
            with self.stream() as stream:
                self._content = stream.read()
        return require(self._content, "_content")

    @content.setter
    def content(self, value: bytes) -> None:
        logger.info(f"{self} reassigning the byte contents")
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
    def null_info(self) -> ZipInfo:
        info = self.info
        info.CRC = 0
        info.file_size = 0
        info.compress_size = 0
        return info


class ResourceIndex:
    """Auto-indexed collection of EPUBResource objects.

    Provides O(1) lookup by filename and by manifest ID,
    while maintaining a stable list for iteration.
    """

    def __init__(self) -> None:
        self._items: list[Resource] = []
        self._by_path: dict[str, Resource] = {}

    def __repr__(self) -> str:
        return f"ResourceIndex({len(self._items)})"

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, item):
        return self._items[item]

    def __contains__(self, item: Resource | str) -> bool:
        if isinstance(item, str):
            return item in self._by_path
        return item in self._items

    @classmethod
    def from_infolist(cls, infolist: list[ZipInfo], stream: Callable[[ZipInfo], BinaryIO]) -> ResourceIndex:
        resource_list = [Resource(info=info, stream_bytes=stream) for info in infolist]
        return cls.from_resource_list(resource_list)

    @classmethod
    def from_resource_list(cls, resource_list: list[Resource]) -> ResourceIndex:
        new_index = ResourceIndex()
        for resource in resource_list:
            new_index.add(resource)
        return new_index

    def add(self, resource) -> None:
        """Add a resource to the index."""
        self._items.append(resource)
        self._by_path[resource.info.filename] = resource

    def remove(self, resource: Resource) -> None:
        """Remove a resource from the index."""
        self._items.remove(resource)
        self._by_path.pop(resource.info.filename, None)
        resource.is_deleted = True

    def by_path(self, path: str) -> Resource | None:
        """Look up a resource by its filename/path."""
        return self._by_path.get(path)

    def by_media_type(self, media_type: MediaType) -> ResourceIndex:
        return ResourceIndex.from_resource_list([r for r in self._items if r.media_type is media_type])

    def by_role(self, role: EpubRole) -> ResourceIndex:
        return ResourceIndex.from_resource_list([r for r in self._items if r.role is role])
