import logging

from library.epub.manifest import EpubManifest
from library.epub.media_type import EpubRole, FileName
from library.epub.resources import ResourceIndex, Resource
from library.epub.xml_models.container_model import ContainerDocument
from library.epub.xml_models.ncx_model import NCXDocument
from library.epub.xml_models.package_document import PackageDocument
from library.asserts import require

logger = logging.getLogger("epub_core")


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
    def package_resource(self) -> Resource:
        if self._package_resource is None:
            opf_resources = self.resources.by_role(EpubRole.OPF)
            if len(opf_resources) != 1:
                container_resource: Resource = require(self.resources.by_path(FileName.CONTAINER), "CONTAINER")
                container_document = ContainerDocument.from_xml_bytes(container_resource.content)
                assert len(container_document.opf_paths) == 1, "EPUB's with several package documents are not supported"
                opf_path = require(container_document.opf_path, "container's opf_path")
                self._package_resource = require(self.resources.by_path(opf_path), "package_resource")
            else:
                self._package_resource = opf_resources[0]
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
            self._manifest = EpubManifest.from_package(
                self.package, self.resources, package_path=self.package_resource.filename
            )
        return require(self._manifest, f"{self} manifest")
