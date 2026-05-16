import logging
from pathlib import Path
from typing import Callable
from zipfile import ZipInfo

from dataclasses import field, dataclass
from hashlib import md5


from epub.utils import SQLITE_MAX_INT
from library.asserts import require
from library.epub.epub_link import EPUBLink

from library.epub.media_type import type_and_role_from_filename, EpubRole, MediaType
from library.epub.resource_mixin import XmlMixin, HtmlMixin, XmlDocumentMixin
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.ncx_model import NavPoint, NCXDocument
from library.epub.xml_models.package_document import PackageDocument
from library.epub.xml_models.package_sequences import ManifestItem, SpineItemRef, GuideReference
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file

logger = logging.getLogger("resource")


@dataclass(kw_only=True, repr=False)
class LinkedResource:
    linked_by: list[EPUBLink] = field(default_factory=list)
    manifest_item: ManifestItem | None = None

    @property
    def id(self) -> str | None:
        if self.manifest_item is not None:
            return self.manifest_item.id
        return None


@dataclass(kw_only=True, repr=False)
class EPUBResource(LinkedResource):
    """Represents a single file in an EPUB archive."""

    info: ZipInfo
    read_bytes_func: Callable[[ZipInfo], bytes]
    media_type: MediaType
    role: EpubRole

    _content: bytes | None = None
    _hex_hash: str | None = None

    is_modified: bool = False
    is_deleted: bool = False

    def __repr__(self) -> str:
        return f"EPUBResource({self.filename!r})"

    def __params__(self) -> str:
        return f"(role={self.role.value!r}, media={self.media_type.value!r})"

    # <editor-fold "Content Parsing Methods">

    def serialize(self) -> bytes | None:
        return None

    def invalidate_parsed_objects(self) -> None:
        self.is_modified = True

    def invalidate_byte_cache(self) -> None:
        """
        MUST be called manually after modifying a parsed object (like .xml or .image) in-place.
        Forces the resource to re-serialize the object the next time .content is accessed.
        """
        self._content = None
        self.is_modified = True

    @property
    def content(self) -> bytes:
        if self._content is None:
            self._content = self.serialize()
        if self._content is None:
            self._content = self.read_bytes_func(self.info)
        return require(self._content)

    @content.setter
    def content(self, value: bytes) -> None:
        logger.debug(f"{self} reassigning the content bytes")
        self._content = value
        self.invalidate_parsed_objects()

    # </editor-fold>

    # <editor-fold "Convenience Methods">

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
    def hash_prefixed_name(self):
        return f"{self.int64_hash}_{Path(self.filename).name}"

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

    # </editor-fold>

    @classmethod
    def from_filesystem_path(cls, path: Path) -> EPUBResource:
        if not path.exists():
            raise ValueError(f"{path} does not exist, cannot create EPUBResource")
        info = ZipInfo.from_file(path, arcname=path.name, strict_timestamps=False)
        return cls(info=info, read_bytes_func=lambda i: Path(i.filename).read_bytes())

    def write_to_filesystem(self, path: Path) -> EPUBResource:
        if path.exists():
            logger.warning(f"{self}, file {path} exists, nothing to write.")
        else:
            byte_count = path.write_bytes(self.content)
            apply_zipinfo_timestamp_to_file(self.info, path)
            logger.info(f"{self}, written {byte_count} bytes to {path}.")
        return EPUBResource.from_filesystem_path(path)

    def get_stats(self) -> dict:
        return {
            "filename": self.info.filename,
            "media_type": self.media_type,
            "manifest_media_type": self.manifest_item and self.manifest_item.media_type,
            "id": self.manifest_item and self.manifest_item.id,
            "links_by": len(self.linked_by),
            "links_to": len(self.linked_to),
            "spine": bool(self.spine_item_ref),
            "guide": bool(self.guide_reference),
            "ncx_label": self.ncx_nav_point and self.ncx_nav_point.nav_label.text,
            "nav": bool(self.navs),
        }


@dataclass(kw_only=True, repr=False)
class EpubXmlResource(XmlMixin, EPUBResource): ...


@dataclass(kw_only=True, repr=False)
class EpubHtmlResource(HtmlMixin, EPUBResource):
    spine_item_ref: SpineItemRef | None = None
    guide_reference: GuideReference | None = None
    source_sequence: int | None = None
    ncx_nav_point: NavPoint | None = None


@dataclass(kw_only=True, repr=False)
class EpubContainerResource(XmlDocumentMixin[ContainerDocument], EPUBResource):
    document_model = ContainerDocument


@dataclass(kw_only=True, repr=False)
class EpubOpfResource(XmlDocumentMixin[PackageDocument], EPUBResource):
    document_model = PackageDocument


@dataclass(kw_only=True, repr=False)
class EpubNcxResource(XmlDocumentMixin[NCXDocument], EPUBResource):
    document_model = NCXDocument


def instantiate_epub_resource(info: ZipInfo, read_bytes_func: Callable[[ZipInfo], bytes]):
    media_type, role = type_and_role_from_filename(info.filename)
    logger.debug(f"info {info.filename!r}, media_type: {media_type.value!r}, role: {role.value!r}")
    match role:
        case EpubRole.HTML:
            return EpubHtmlResource(info=info, read_bytes_func=read_bytes_func, media_type=media_type, role=role)
        case EpubRole.XML:
            return EpubXmlResource(info=info, read_bytes_func=read_bytes_func, media_type=media_type, role=role)
        case EpubRole.OPF:
            return EpubOpfResource(info=info, read_bytes_func=read_bytes_func, media_type=media_type, role=role)
        case EpubRole.NCX:
            return EpubNcxResource(info=info, read_bytes_func=read_bytes_func, media_type=media_type, role=role)
        case EpubRole.CONTAINER:
            return EpubContainerResource(info=info, read_bytes_func=read_bytes_func, media_type=media_type, role=role)
    return EPUBResource(info=info, read_bytes_func=read_bytes_func, media_type=media_type, role=role)