import logging
import re
from collections.abc import Iterator
from enum import StrEnum

from library.epub.epub_link import EPUBLink
from library.epub.manifest import EpubManifest
from library.epub.media_type import MediaType, EpubRole, FileName
from library.epub.resources import ResourceIndex, Resource
from library.epub.utils_href import posix_absolute_href
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.ncx_model import NCXDocument, NavPoint
from library.epub.xml_models.nav_model import NavDocument, NavListItem
from library.epub.xml_models.package_document import PackageDocument
from library.asserts import require

logger = logging.getLogger("epub_core")


class EpubSpecification(StrEnum):
    UNKNOWN = "UNKNOWN"
    EPUB_MIMETYPE = "EPUB_MIMETYPE"
    EPUB_CONTAINER = "EPUB_CONTAINER"
    SERENE_PANDA_ENCRYPTED = "SERENE_PANDA_ENCRYPTED"
    SERENE_PANDA_UNENCRYPTED = "SERENE_PANDA_UNENCRYPTED"
    ASIA_NOVEL = "ASIA_NOVEL"
    CALIBRE = "CALIBRE"
    WEB_TO_EPUB = "WEB_TO_EPUB"
    EPUB_PRESS = "EPUB_PRESS"
    EWA_ONE = "EWA_ONE"


class EpubCore:
    """Manages the structural core of an EPUB archive."""

    def __init__(self, resources: ResourceIndex) -> None:
        self.resources = resources

        self._package_resource: Resource | None = None
        self._package_document: PackageDocument | None = None
        self._ncx_resource: Resource | None = None
        self._ncx_document: NCXDocument | None = None

        self._manifest: EpubManifest | None = None

    def __repr__(self):
        return f"EpubCore({len(self.resources)})"

    @property
    def ___opf_resource(self):
        # More reliable but slower
        if self._package_resource is None:
            mimetype_resource = require(self.resources.by_path(FileName.MIMETYPE), "MIMETYPE")
            container_resource: Resource = require(self.resources.by_path(FileName.CONTAINER), "CONTAINER")
            container_document = ContainerDocument.from_xml_bytes(container_resource.content)
            assert len(container_document.opf_paths) == 1, "EPUB's with several package documents are not supported"
            opf_path = require(container_document.opf_path, "opf_path")
            self._package_resource = require(self.resources.by_path(opf_path), "package_resource")
        assert self._package_resource is not None, f"{self} opf_resource was found."
        return self._package_resource

    @property
    def package_resource(self) -> Resource:
        if self._package_resource is None:
            opfs = self.resources.by_role(EpubRole.OPF)
            if len(opfs) != 1:
                raise NotImplementedError("EPUB's with several package documents are not supported")
            self._package_resource = opfs[0]
        return require(self._package_resource, f"{self} package_resource")

    @property
    def package(self) -> PackageDocument:
        if self._package_document is None:
            self._package_document = PackageDocument.from_xml_bytes(self.package_resource.content)
        return require(self._package_document, f"{self} package")

    @property
    def ncx_resource(self) -> Resource:
        if self._ncx_resource is None:
            ncxs = self.resources.by_role(EpubRole.NCX)
            if len(ncxs) != 1:
                raise NotImplementedError("EPUB's with several ncx documents are not supported")
            self._ncx_resource = ncxs[0]
        return require(self._ncx_resource, f"{self} ncx_resource")

    @property
    def ncx(self) -> NCXDocument:
        if self._ncx_document is None:
            self._ncx_document = NCXDocument.from_xml_bytes(self.ncx_resource.content)
        return require(self._ncx_document, f"{self} ncx")

    @property
    def manifest(self) -> EpubManifest:
        if self._manifest is None:
            self._manifest = EpubManifest.from_package(self.package, self.resources)
        return require(self._manifest, f"{self} manifest")
