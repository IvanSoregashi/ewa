import logging

from library.epub.manifest import EpubManifest
from library.epub.media_type import EpubRole
from library.epub.package import EpubPackage
from library.epub.resources import Resource
from library.epub.xml_models.ncx_model import NCXDocument
from library.epub.xml_models.package_document import PackageDocument
from library.asserts import require

logger = logging.getLogger("epub_core")


class EpubCore:
    """Compatibility access to package, manifest and NCX during the package prototype."""

    def __init__(self, package: EpubPackage) -> None:
        self.epub_package = package
        self.resources = package.resources

        self._ncx_resource: Resource | None = None
        self._ncx_document: NCXDocument | None = None

        self._manifest: EpubManifest | None = None

    def __repr__(self):
        return f"EpubCore({len(self.resources)})"

    @property
    def package_resource(self) -> Resource:
        return self.epub_package.resource

    @property
    def package(self) -> PackageDocument:
        return self.epub_package.document

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
            self._manifest = EpubManifest.from_package(self.epub_package)
        return require(self._manifest, f"{self} manifest")
