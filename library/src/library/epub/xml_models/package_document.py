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
        """Collect IDs from the current parsed model, including every OPF section.

        Recomputed so direct edits are visible; this is not duplicate-ID validation.
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
