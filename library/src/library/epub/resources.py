import io
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable, BinaryIO, Iterator, Generator, ContextManager
from zipfile import ZipInfo

from lxml import html, etree
from lxml.html import HtmlElement
from lxml.etree import Element
from hashlib import md5
from PIL import Image


from epub.utils import SQLITE_MAX_INT
from library.epub.epub_link import EPUBLink

from library.epub.media_type import type_and_role_from_filename, EpubRole, MediaType
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.nav_model import NavDocument
from library.epub.xml_models.ncx_model import NavPoint, NCXDocument
from library.epub.xml_models.package_document import PackageDocument
from library.epub.xml_models.package_sequences import ManifestItem, SpineItemRef, GuideReference
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file
from library.image.optimization import optimization_machine, get_image_info
from library.xml.document_pydantic import XMLDocumentModel
from library.xml.utils import etree_from_bytes

logger = logging.getLogger("resource")


@dataclass(kw_only=True)
class LazyLoadFile:
    info: ZipInfo
    # read_bytes: Callable[[ZipInfo], bytes]
    stream_bytes: Callable[[ZipInfo], BinaryIO]

    _content: bytes | None = field(default=None, init=False, repr=False)
    _hex_hash: str | None = None

    def __repr__(self) -> str:
        return f"LazyLoadFile({self.info.filename!r})"

    @classmethod
    def from_filesystem_path(cls, path: Path):
        if not path.exists():
            raise ValueError(f"{path} does not exist, cannot create LazyLoadFile")
        info = ZipInfo.from_file(path, strict_timestamps=False)
        media_type, role = type_and_role_from_filename(info.filename)
        return cls(info=info, stream_bytes=lambda i: Path(i.filename).open("rb"), role=role, media_type=media_type)

    @contextmanager
    def stream(self) -> Generator[BinaryIO, None, None]:
        if self._content is not None:
            yield io.BytesIO(self._content)
        else:
            with self.stream_bytes(self.info) as stream:
                yield stream

    @property
    def content(self) -> bytes:
        if self._content is None:
            with self.stream() as stream:
                self._content: bytes = stream.read()
        return self._content

    @content.setter
    def content(self, value: bytes) -> None:
        logger.info(f"{self} reassigning the byte contents")
        # TODO should this even exist? set the modified flag?
        self._content = value

    @property
    def hex_hash(self) -> str:
        if self._hex_hash is None:
            self._hex_hash: str = md5(self.content).hexdigest()
        return self._hex_hash

    @property
    def int64_hash(self):
        return int(self.hex_hash, 16) % SQLITE_MAX_INT

    @property
    def hash_prefixed_name(self):
        return f"{self.int64_hash}_{Path(self.info.filename).name}"

    def write_to_filesystem(self, path: Path) -> LazyLoadFile:
        if path.exists():
            logger.warning(f"{self}, file {path} exists, nothing to write.")
        else:
            byte_count = path.write_bytes(self.content)
            apply_zipinfo_timestamp_to_file(self.info, path)
            logger.debug(f"{self}, written {byte_count} bytes to {path}.")
        return self.__class__.from_filesystem_path(path)


@dataclass(kw_only=True)
class LazyLoadXmlFile(LazyLoadFile):
    _xml: Element | None = None

    @property
    def xml(self) -> Element:
        if self._xml is None:
            self._xml: Element = etree_from_bytes(self.content)
        return self._xml


@dataclass(kw_only=True)
class LazyLoadHtmlFile(LazyLoadFile):
    _html: HtmlElement | None = None

    @property
    def html(self) -> HtmlElement:
        if self._html is None:
            self._html: HtmlElement = html.document_fromstring(self.content)
        return self._html

    def parse_links(self) -> list[EPUBLink]:
        return [EPUBLink.from_iterlinks(self.info.filename, link_data) for link_data in self.html.iterlinks()]


@dataclass(kw_only=True)
class LazyLoadXmlDocumentFile[D: XMLDocumentModel](LazyLoadFile):
    document_model: type[D] | None = None
    _document: D | None = None

    @property
    def document(self):
        if self._document is None:
            self._document: D = self.document_model.from_xml_bytes(self.content)
        return self._document


@dataclass(kw_only=True)
class LazyLoadImageFile(LazyLoadFile):
    @contextmanager
    def stream_image(self) -> Generator[Image.Image, None, None]:
        with self.stream() as stream:
            with Image.open(stream) as img:
                yield img


@dataclass(kw_only=True)
class PackagedResource:
    linked_by: list[EPUBLink] = field(default_factory=list)

    manifest_item: ManifestItem | None = None

    @property
    def id(self) -> str | None:
        if self.manifest_item:
            return self.manifest_item.id
        return None


@dataclass(kw_only=True)
class DocumentWithLinks(PackagedResource):
    linked_to: list[EPUBLink] = field(default_factory=list)

    spine_item_ref: SpineItemRef | None = None
    guide_reference: GuideReference | None = None
    source_sequence: int | None = None
    ncx_nav_point: NavPoint | None = None


@dataclass(kw_only=True)
class RoleBasedResource:
    media_type: MediaType
    role: EpubRole
    is_modified = False
    is_deleted = False

    def type_and_role_params(self) -> str:
        return f"({self.media_type.value!r}, {self.role.value!r})"


@dataclass(kw_only=True)
class EpubDefaultResource(RoleBasedResource, PackagedResource, LazyLoadFile): ...


@dataclass(kw_only=True)
class EpubXmlResource(RoleBasedResource, PackagedResource, LazyLoadXmlFile): ...


@dataclass(kw_only=True)
class EpubHtmlResource(RoleBasedResource, LazyLoadHtmlFile, DocumentWithLinks): ...


@dataclass(kw_only=True)
class EpubContainerResource(RoleBasedResource, LazyLoadXmlDocumentFile[ContainerDocument]):
    document_model: type[ContainerDocument] = ContainerDocument


@dataclass(kw_only=True)
class EpubPackageResource(RoleBasedResource, LazyLoadXmlDocumentFile[PackageDocument]):
    document_model: type[PackageDocument] = PackageDocument


@dataclass(kw_only=True)
class EpubNcxResource(RoleBasedResource, PackagedResource, LazyLoadXmlDocumentFile[NCXDocument]):
    document_model: type[NCXDocument] = NCXDocument


@dataclass(kw_only=True)
class EpubNavResource(EpubHtmlResource, LazyLoadXmlDocumentFile[NavDocument]):
    document_model: type[NavDocument] = NavDocument  # Not tested


@dataclass(kw_only=True)
class EpubImageResource(RoleBasedResource, PackagedResource, LazyLoadImageFile):
    # png cases:
    # - rgb
    # - rgba + transparency
    # - rgba + no transparency
    # - compression?
    # jpg cases:
    # - jpg (quality? loading?)
    # -
    # gif cases:
    # - P mode
    # - version b'GIF89a' |
    # - background + transparency + duration headers

    def optimize(self, max_width: int = 1080, max_height: int = 0, convert_rgb_to_jpg: bool = True) -> None | Path:
        if self.info.file_size < 50 * 1024:  # 50kb
            return None
        with self.stream_image() as image:
            original_format = image.format
            if original_format is None:
                logger.warning(f"{self} unknown original format of the image.")
            buffer = BytesIO()
            result = optimization_machine(image, buffer=buffer, filesize=self.info.file_size)

            self.is_modified = True
            buffer = BytesIO()
            new_path = None
            if image.mode == "RGB" and (original_format == "JPEG" or convert_rgb_to_jpg):
                image.save(buffer, optimize=True, format="JPEG", quality=85)
                new_path = Path(self.info.filename).with_suffix(".jpg")
            else:
                logger.warning(f"{self} Image of unusual format {image.mode, original_format} was modified.")
                image.save(buffer, optimize=True, format=original_format)
            self.content = buffer.getvalue()
            return new_path

    def get_info(self):
        with self.stream_image() as image:
            return get_image_info(image=image, filesize=self.info.file_size)

AnyResource = (
    EpubHtmlResource
    | EpubContainerResource
    | EpubPackageResource
    | EpubXmlResource
    | EpubDefaultResource
    | EpubNcxResource
)


def get_resource_stats(resource) -> dict:
    return {
        "filename": resource.info.filename,
        "media_type": resource.media_type,
        "manifest_media_type": resource.manifest_item and resource.manifest_item.media_type,
        "id": resource.manifest_item and resource.manifest_item.id,
        "spine": bool(resource.spine_item_ref),
        "links_to": len(resource.linked_to),
        "links_by": len(resource.linked_by),
        "guide": bool(resource.guide_reference),
        "ncx_label": resource.ncx_nav_point and resource.ncx_nav_point.nav_label.text,
        "nav": bool(resource.navs),
    }


def get_epub_class_by_role(role: EpubRole):
    match role:
        case EpubRole.HTML:
            resource_class = EpubHtmlResource
        case EpubRole.NCX:
            resource_class = EpubNcxResource
        case EpubRole.OPF:
            resource_class = EpubPackageResource
        case EpubRole.CONTAINER:
            resource_class = EpubContainerResource
        case EpubRole.XML:
            resource_class = EpubXmlResource
        case EpubRole.IMAGE:
            resource_class = EpubImageResource
        case _:
            resource_class = EpubDefaultResource

    return resource_class


def instantiate_resource(info: ZipInfo, stream_bytes: Callable[[ZipInfo], BinaryIO]):
    media_type, role = type_and_role_from_filename(info.filename)
    resource_class = get_epub_class_by_role(role)

    return resource_class(info=info, stream_bytes=stream_bytes, role=role, media_type=media_type)


class OldEPUBResource:
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
    def from_filesystem_path(cls, path: Path) -> OldEPUBResource:
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

    def write_to_filesystem(self, path: Path) -> OldEPUBResource:
        if path.exists():
            logger.warning(f"{self}, file {path} exists, nothing to write.")
        else:
            byte_count = path.write_bytes(self.content)
            apply_zipinfo_timestamp_to_file(self.info, path)
            logger.info(f"{self}, written {byte_count} bytes to {path}.")
        return OldEPUBResource.from_filesystem_path(path)

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
