from pydantic_xml import attr, element

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
