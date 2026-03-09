from pydantic_xml import BaseXmlModel, attr, element
from library.xml.document_pydantic import XMLDocumentModel
from library.epub.epub_namespaces import OPF_NSMAP
from library.epub.concepts.metadata import DCMetadataType


class DCElement(BaseXmlModel, ns="dc", nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    lang: str | None = attr(name="lang", ns="xml", default=None)
    type: str | None = attr(name="type", ns="xsi", default=None)

    file_as: str | None = attr(name="file-as", default=None)
    file_as_ns: str | None = attr(name="file-as", ns="opf", default=None)
    role: str | None = attr(name="role", default=None)
    role_ns: str | None = attr(name="role", ns="opf", default=None)
    scheme: str | None = attr(name="scheme", default=None)
    scheme_ns: str | None = attr(name="scheme", ns="opf", default=None)
    event: str | None = attr(name="event", default=None)
    event_ns: str | None = attr(name="event", ns="opf", default=None)

    name: str | None = attr(default=None)
    content_attr: str | None = attr(name="content", default=None)
    text: str | None = None


class DCMeta(DCElement, tag="meta"):
    pass


class Meta(DCElement, tag="meta", ns="opf"):
    property: str | None = attr(default=None)
    refines: str | None = attr(default=None)


class Metadata(BaseXmlModel, tag="metadata", ns="opf", nsmap=OPF_NSMAP, search_mode="unordered"):
    titles: list[DCElement] = element(tag="title", default=[])
    creators: list[DCElement] = element(tag="creator", default=[])
    subjects: list[DCElement] = element(tag="subject", default=[])
    descriptions: list[DCElement] = element(tag="description", default=[])
    publishers: list[DCElement] = element(tag="publisher", default=[])
    contributors: list[DCElement] = element(tag="contributor", default=[])
    dates: list[DCElement] = element(tag="date", default=[])
    types: list[DCElement] = element(tag="type", default=[])
    formats: list[DCElement] = element(tag="format", default=[])
    identifiers: list[DCElement] = element(tag="identifier", default=[])
    sources: list[DCElement] = element(tag="source", default=[])
    languages: list[DCElement] = element(tag="language", default=[])
    relations: list[DCElement] = element(tag="relation", default=[])
    coverages: list[DCElement] = element(tag="coverage", default=[])
    rights: list[DCElement] = element(tag="rights", default=[])
    metas: list[Meta] = element(tag="meta", default=[])
    dc_metas: list[DCMeta] = element(tag="meta", default=[])

    @property
    def title(self) -> DCElement:
        return self.titles[0] if self.titles else None

    @property
    def language(self) -> DCElement:
        return self.languages[0] if self.languages else None

    def add_metadata(self, tag: str | DCMetadataType, text: str, dc: bool = True, **kwargs):
        """Uniform helper to add metadata items."""
        if dc:
            new_item = DCElement(text=text, **kwargs)
            # Find matching list: titles, creators, etc.
            attr_name = f"{tag}s"
            if hasattr(self, attr_name):
                getattr(self, attr_name).append(new_item)
        else:
            # EPUB 3 style <meta property="...">
            new_item = Meta(text=text, **kwargs)
            self.metas.append(new_item)


class ManifestItem(BaseXmlModel, tag="item", ns="opf", nsmap=OPF_NSMAP):
    id: str = attr()
    href: str = attr()
    media_type: str = attr(name="media-type")
    properties: str | None = attr(default=None)
    fallback: str | None = attr(default=None)
    overlay: str | None = attr(default=None)


class Manifest(BaseXmlModel, tag="manifest", ns="opf", nsmap=OPF_NSMAP):
    items: list[ManifestItem] = element(tag="item", default=[])


class SpineItemRef(BaseXmlModel, tag="itemref", ns="opf", nsmap=OPF_NSMAP):
    idref: str = attr()
    linear: str | None = attr(default=None)
    properties: str | None = attr(default=None)
    id: str | None = attr(default=None)


class Spine(BaseXmlModel, tag="spine", ns="opf", nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    toc: str | None = attr(default=None)
    page_progression_direction: str | None = attr(name="page-progression-direction", default=None)
    page_map: str | None = attr(name="page-map", default=None)
    itemrefs: list[SpineItemRef] = element(tag="itemref", default=[])


class GuideReference(BaseXmlModel, tag="reference", ns="opf", nsmap=OPF_NSMAP):
    type: str = attr()
    title: str | None = attr(default=None)
    href: str = attr()


class Guide(BaseXmlModel, tag="guide", ns="opf", nsmap=OPF_NSMAP):
    references: list[GuideReference] = element(tag="reference", default=[])


class Tour(BaseXmlModel, tag="tour", ns="opf", nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    title: str = attr()


class Tours(BaseXmlModel, tag="tours", ns="opf", nsmap=OPF_NSMAP):
    tours: list[Tour] = element(tag="tour", default=[])


class PackageDocument(XMLDocumentModel, tag="package", ns="opf", nsmap=OPF_NSMAP, search_mode="unordered"):
    version: str | None = attr(default=None)
    unique_identifier: str | None = attr(name="unique-identifier", default=None)
    id: str | None = attr(default=None)
    prefix: str | None = attr(default=None)
    lang: str | None = attr(name="lang", ns="xml", default=None)
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
