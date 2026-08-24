from library.xml.document_pydantic import XMLDocumentModel

from pydantic_xml import BaseXmlModel, RootXmlModel, attr, element
from library.epub.epub_namespaces import NamespacePrefix, CONTAINER_NSMAP


class RootFile(BaseXmlModel, tag="rootfile", ns=NamespacePrefix.CONTAINER, nsmap=CONTAINER_NSMAP):
    full_path: str = attr(name="full-path")
    media_type: str = attr(name="media-type")


class RootFiles(RootXmlModel, tag="rootfiles", ns=NamespacePrefix.CONTAINER, nsmap=CONTAINER_NSMAP):
    root: list[RootFile] = element(tag="rootfile", ns=NamespacePrefix.CONTAINER, default=[])


class ContainerDocument(XMLDocumentModel, tag="container", ns=NamespacePrefix.CONTAINER, nsmap=CONTAINER_NSMAP):
    version: str = attr()
    rootfiles_wrapper: RootFiles = element(tag="rootfiles", ns=NamespacePrefix.CONTAINER, default=[])

    @property
    def rootfiles(self) -> list[RootFile]:
        if self.rootfiles_wrapper:
            return self.rootfiles_wrapper.root
        return []

    @property
    def opf_path(self) -> str | None:
        """Returns the full-path of the first OEBPS package rootfile."""
        for rootfile in self.rootfiles:
            if rootfile.media_type == "application/oebps-package+xml":
                return rootfile.full_path
        return None

    @property
    def opf_paths(self) -> list[str]:
        return [rootfile.full_path for rootfile in self.rootfiles]

    @classmethod
    def standard(cls, opf_path: str) -> "ContainerDocument":
        """A minimal container pointing at a single package document."""
        return cls(
            version="1.0",
            rootfiles_wrapper=RootFiles(
                root=[RootFile(full_path=opf_path, media_type="application/oebps-package+xml")]
            ),
        )
