from library.epub.epub_namespaces import XMLNamespace
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, ChildField, ChildListField


class RootFile(XMLElement, tag="rootfile", ns=XMLNamespace.CONTAINER):
    full_path = AttrField("full-path")
    media_type = AttrField("media-type")


class RootFiles(XMLElement, tag="rootfiles", ns=XMLNamespace.CONTAINER):
    items = ChildListField(RootFile)


class ContainerDocument(XMLDocumentSchema, tag="container", ns=XMLNamespace.CONTAINER):
    version = AttrField("version")
    rootfiles_wrapper = ChildField(RootFiles, tag="rootfiles")

    @property
    def rootfiles(self) -> list[RootFile]:
        if self.rootfiles_wrapper:
            return self.rootfiles_wrapper.items
        return []

    @property
    def opf_path(self) -> str | None:
        """Returns the full-path of the first OEBPS package rootfile."""
        for rootfile in self.rootfiles:
            if rootfile.media_type == "application/oebps-package+xml":
                return rootfile.full_path
        return None
