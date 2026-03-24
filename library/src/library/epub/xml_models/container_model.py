from pydantic_xml import BaseXmlModel, attr, element
from library.epub.epub_namespaces import XMLNamespace, NamespacePrefix, CONTAINER_NSMAP
from library.xml.document_pydantic import XMLDocumentModel


class RootFile(BaseXmlModel, tag="rootfile", ns=NamespacePrefix.CONTAINER, nsmap=CONTAINER_NSMAP):
    full_path: str = attr(name="full-path")
    media_type: str = attr(name="media-type")


class RootFiles(BaseXmlModel, tag="rootfiles", ns=NamespacePrefix.CONTAINER, nsmap=CONTAINER_NSMAP):
    items: list[RootFile] = element(tag="rootfile", ns=NamespacePrefix.CONTAINER, default=[])


class ContainerDocument(XMLDocumentModel, tag="container", ns=NamespacePrefix.CONTAINER, nsmap=CONTAINER_NSMAP):
    version: str = attr()
    rootfiles_wrapper: RootFiles = element(tag="rootfiles", ns=NamespacePrefix.CONTAINER)

    @property
    def rootfiles(self) -> list[RootFile]:
        return self.rootfiles_wrapper.items if self.rootfiles_wrapper else []

    @property
    def opf_path(self) -> str | None:
        """Returns the full-path of the first OEBPS package rootfile."""
        for rootfile in self.rootfiles:
            if rootfile.media_type == "application/oebps-package+xml":
                return rootfile.full_path
        return None
