from pydantic_xml import BaseXmlModel, attr, element
from library.xml.document_pydantic import XMLDocumentModel
from library.epub.epub_namespaces import OPF_NSMAP, NamespacePrefix
from library.epub.concepts.metadata import DCMetadataType


class DCElement(BaseXmlModel, ns=NamespacePrefix.DC, nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    lang: str | None = attr(name="lang", ns=NamespacePrefix.XML, default=None)
    type: str | None = attr(name="type", ns=NamespacePrefix.XSI, default=None)

    file_as: str | None = attr(name="file-as", default=None)
    file_as_ns: str | None = attr(name="file-as", ns=NamespacePrefix.OPF, default=None)
    role: str | None = attr(name="role", default=None)
    role_ns: str | None = attr(name="role", ns=NamespacePrefix.OPF, default=None)
    scheme: str | None = attr(name="scheme", default=None)
    scheme_ns: str | None = attr(name="scheme", ns=NamespacePrefix.OPF, default=None)
    event: str | None = attr(name="event", default=None)
    event_ns: str | None = attr(name="event", ns=NamespacePrefix.OPF, default=None)

    name: str | None = attr(default=None)
    content_attr: str | None = attr(name="content", default=None)
    text: str | None = None


class DCMeta(DCElement, tag="meta"):
    pass


class Meta(DCElement, tag="meta", ns=NamespacePrefix.OPF):
    property: str | None = attr(default=None)
    refines: str | None = attr(default=None)


class Metadata(BaseXmlModel, tag="metadata", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP, search_mode="unordered"):
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

    def remove_metadata(
        self, tag: str | DCMetadataType, text: str | None = None, id: str | None = None, dc: bool = True
    ):
        """Uniform helper to remove metadata items."""
        def should_remove(item) -> bool:
            if text is None and id is None:
                return True
            match_text = (text is None) or (getattr(item, "text", None) == text)
            match_id = (id is None) or (getattr(item, "id", None) == id)
            return match_text and match_id

        if dc:
            attr_name = f"{tag}s"
            if hasattr(self, attr_name):
                current = getattr(self, attr_name)
                setattr(self, attr_name, [x for x in current if not should_remove(x)])
        else:
            self.metas = [x for x in self.metas if not should_remove(x)]


class ManifestItem(BaseXmlModel, tag="item", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    id: str = attr()
    href: str = attr()
    media_type: str = attr(name="media-type")
    properties: str | None = attr(default=None)
    fallback: str | None = attr(default=None)
    overlay: str | None = attr(default=None)


class Manifest(BaseXmlModel, tag="manifest", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    items: list[ManifestItem] = element(tag="item", default=[])

    def add_item(self, id: str, href: str, media_type: str, **kwargs) -> ManifestItem:
        new_item = ManifestItem(id=id, href=href, media_type=media_type, **kwargs)
        self.items.append(new_item)
        return new_item

    def remove_item(self, item: ManifestItem | None = None, id: str | None = None):
        """Remove a manifest item by its id or object reference."""
        if item is not None:
            self.items = [i for i in self.items if i is not item]
        elif id is not None:
            self.items = [i for i in self.items if i.id != id]


class SpineItemRef(BaseXmlModel, tag="itemref", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    idref: str = attr()
    linear: str | None = attr(default=None)
    properties: str | None = attr(default=None)
    id: str | None = attr(default=None)


class Spine(BaseXmlModel, tag="spine", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    toc: str | None = attr(default=None)
    page_progression_direction: str | None = attr(name="page-progression-direction", default=None)
    page_map: str | None = attr(name="page-map", default=None)
    itemrefs: list[SpineItemRef] = element(tag="itemref", default=[])

    def add_itemref(self, idref: str, linear: str | None = None, **kwargs) -> SpineItemRef:
        new_ref = SpineItemRef(idref=idref, linear=linear, **kwargs)
        self.itemrefs.append(new_ref)
        return new_ref

    def remove_itemref(self, itemref: SpineItemRef | None = None, idref: str | None = None):
        """Remove a spine itemref by its idref or object reference."""
        if itemref is not None:
            self.itemrefs = [r for r in self.itemrefs if r is not itemref]
        elif idref is not None:
            self.itemrefs = [r for r in self.itemrefs if r.idref != idref]


class GuideReference(BaseXmlModel, tag="reference", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    type: str = attr()
    title: str | None = attr(default=None)
    href: str = attr()


class Guide(BaseXmlModel, tag="guide", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    references: list[GuideReference] = element(tag="reference", default=[])

    def add_reference(self, type: str, href: str, title: str | None = None, **kwargs) -> GuideReference:
        new_ref = GuideReference(type=type, href=href, title=title, **kwargs)
        self.references.append(new_ref)
        return new_ref

    def remove_reference(self, reference: GuideReference | None = None, type: str | None = None):
        """Remove a guide reference by its type or object reference."""
        if reference is not None:
            self.references = [r for r in self.references if r is not reference]
        elif type is not None:
            self.references = [r for r in self.references if r.type != type]


class Tour(BaseXmlModel, tag="tour", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    id: str | None = attr(default=None)
    title: str = attr()


class Tours(BaseXmlModel, tag="tours", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP):
    tours: list[Tour] = element(tag="tour", default=[])

    def add_tour(self, id: str, title: str, **kwargs) -> Tour:
        new_tour = Tour(id=id, title=title, **kwargs)
        self.tours.append(new_tour)
        return new_tour

    def remove_tour(self, tour: Tour | None = None, id: str | None = None):
        """Remove a tour by its id or object reference."""
        if tour is not None:
            self.tours = [t for t in self.tours if t is not tour]
        elif id is not None:
            self.tours = [t for t in self.tours if t.id != id]


class PackageDocument(
    XMLDocumentModel, tag="package", ns=NamespacePrefix.OPF, nsmap=OPF_NSMAP, search_mode="unordered"
):
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
