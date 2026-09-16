from pydantic_xml import BaseXmlModel, attr, element

from library.epub.xml_models.package_metadata import Metadata
from library.epub.xml_models.package_sequences import Manifest, Spine, Guide, Tours
from library.xml.document_pydantic import XMLDocumentModel
from library.epub.epub_namespaces import OPF_NSMAP, NamespacePrefix


class PackageDocument(XMLDocumentModel, tag="package", ns="", nsmap=OPF_NSMAP, search_mode="unordered"):
    version: str | None = attr(default=None)
    unique_identifier: str | None = attr(name="unique-identifier", default=None)
    id: str | None = attr(default=None)
    prefix: str | None = attr(default=None)
    lang: str | None = attr(name="lang", ns=NamespacePrefix.XML, default=None)
    dir: str | None = attr(default=None)

    metadata: Metadata = element()
    manifest: Manifest = element()
    spine: Spine = element()
    guide: Guide | None = element(default=None)
    tours: Tours | None = element(default=None)

    @property
    def ids(self) -> set[str]:
        """Return the set of element IDs currently present in the parsed OPF.

        Includes the package itself, metadata, manifest items, spine entries,
        and other modeled sections. For example, "cover" in document.ids checks
        whether that ID is already occupied before adding a declaration.

        Walks the existing models without serializing XML. Each access builds a
        fresh set so direct edits are reflected; changing the returned set does
        not change the document. Duplicate IDs collapse into one set entry,
        so this checks existence, not uniqueness or validity. Attributes not
        represented by the parsed models and IDs in NCX/NAV are not included.
        """

        def collect(model: BaseXmlModel):
            identifier = getattr(model, "id", None)
            if identifier is not None:
                yield identifier
            for name in type(model).model_fields:
                value = getattr(model, name)
                if isinstance(value, BaseXmlModel):
                    yield from collect(value)
                elif isinstance(value, list):
                    for child in value:
                        if isinstance(child, BaseXmlModel):
                            yield from collect(child)

        return set(collect(self))

    __unordered_tags__ = {
        "package",
        "metadata",
        "manifest",
        "guide",
        "tours",
        "title",
        "creator",
        "subject",
        "description",
        "publisher",
        "contributor",
        "date",
        "type",
        "format",
        "identifier",
        "source",
        "language",
        "relation",
        "coverage",
        "rights",
        "meta",
    }
