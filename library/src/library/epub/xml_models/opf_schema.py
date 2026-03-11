"""
PackageDocument — descriptor-based model for EPUB OPF files.
Mirrors xml_pydantic/package_document.py without pydantic-xml.
"""

from library.epub.epub_namespaces import XMLNamespace, OPF_NSMAP
from library.epub.concepts.metadata import DCMetadataType
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, TextField, ChildField, ChildListField


# ---------------------------------------------------------------------------
# Metadata elements
# ---------------------------------------------------------------------------


class DCElement(XMLElement, ns=XMLNamespace.DC):
    """Base for Dublin Core elements — lives in dc: namespace."""

    id = AttrField("id")
    lang = AttrField("lang", ns=XMLNamespace.XML)
    type = AttrField("type", ns=XMLNamespace.XSI)

    file_as = AttrField("file-as")
    file_as_ns = AttrField("file-as", ns=XMLNamespace.OPF)
    role = AttrField("role")
    role_ns = AttrField("role", ns=XMLNamespace.OPF)
    scheme = AttrField("scheme")
    scheme_ns = AttrField("scheme", ns=XMLNamespace.OPF)
    event = AttrField("event")
    event_ns = AttrField("event", ns=XMLNamespace.OPF)

    name = AttrField("name")
    content_attr = AttrField("content")

    text = TextField()


class DCMeta(DCElement, tag=MetadataType.DC_META, ns=XMLNamespace.DC):
    """<meta> in the dc/opf namespace (old EPUB 2 style)."""


class Meta(DCElement, tag=MetadataType.META, ns=XMLNamespace.OPF):
    """<meta> in the opf namespace (EPUB 3 style)."""

    property = AttrField("property")
    refines = AttrField("refines")


class Metadata(XMLElement, tag="metadata", ns=XMLNamespace.OPF):
    titles = ChildListField(DCElement, tag=DCMetadataType.TITLE)
    creators = ChildListField(DCElement, tag=DCMetadataType.CREATOR)
    subjects = ChildListField(DCElement, tag=DCMetadataType.SUBJECT)
    descriptions = ChildListField(DCElement, tag=DCMetadataType.DESCRIPTION)
    publishers = ChildListField(DCElement, tag=DCMetadataType.PUBLISHER)
    contributors = ChildListField(DCElement, tag=DCMetadataType.CONTRIBUTOR)
    dates = ChildListField(DCElement, tag=DCMetadataType.DATE)
    types = ChildListField(DCElement, tag=DCMetadataType.TYPE)
    formats = ChildListField(DCElement, tag=DCMetadataType.FORMAT)
    identifiers = ChildListField(DCElement, tag=DCMetadataType.IDENTIFIER)
    sources = ChildListField(DCElement, tag=DCMetadataType.SOURCE)
    languages = ChildListField(DCElement, tag=DCMetadataType.LANGUAGE)
    relations = ChildListField(DCElement, tag=DCMetadataType.RELATION)
    coverages = ChildListField(DCElement, tag=DCMetadataType.COVERAGE)
    rights = ChildListField(DCElement, tag=DCMetadataType.RIGHTS)

    metas = ChildListField(Meta)  # default tag/ns from Meta
    dc_metas = ChildListField(DCMeta)  # default tag/ns from DCMeta

    @property
    def title(self) -> DCElement:
        return self.titles[0] if self.titles else None

    @property
    def language(self) -> DCElement:
        return self.languages[0] if self.languages else None

    def add_metadata(self, tag: DCMetadataType | MetadataType, text: str, dc: bool = True, **kwargs):
        """Uniform helper to add metadata items."""
        if dc:
            new_item = DCElement.create(tag=tag, text=text, **kwargs)
            attr_name = f"{tag}s"
            if hasattr(self, attr_name):
                current = getattr(self, attr_name)
                setattr(self, attr_name, current + [new_item])
        else:
            new_item = Meta.create(text=text, **kwargs)
            self.metas = self.metas + [new_item]

    def remove_metadata(
        self, tag: DCMetadataType | MetadataType, text: str | None = None, id: str | None = None, dc: bool = True
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
                current = getattr(self, attr_name, [])
                setattr(self, attr_name, [x for x in current if not should_remove(x)])
        else:
            self.metas = [x for x in self.metas if not should_remove(x)]


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class ManifestItem(XMLElement, tag="item", ns=XMLNamespace.OPF):
    id = AttrField("id")
    href = AttrField("href")
    media_type = AttrField("media-type")
    properties = AttrField("properties")
    fallback = AttrField("fallback")
    overlay = AttrField("overlay")


class Manifest(XMLElement, tag="manifest", ns=XMLNamespace.OPF):
    items = ChildListField(ManifestItem)

    def add_item(self, id: str, href: str, media_type: str, **kwargs) -> ManifestItem:
        new_item = ManifestItem.create(id=id, href=href, media_type=media_type, **kwargs)
        self.items = self.items + [new_item]
        return new_item

    def remove_item(self, item: ManifestItem | None = None, id: str | None = None):
        """Remove a manifest item by its id or object reference."""
        if item is not None:
            self.items = [i for i in self.items if i._elem is not item._elem]
        elif id is not None:
            self.items = [i for i in self.items if i.id != id]


# ---------------------------------------------------------------------------
# Spine
# ---------------------------------------------------------------------------


class SpineItemRef(XMLElement, tag="itemref", ns=XMLNamespace.OPF):
    idref = AttrField("idref")
    linear = AttrField("linear")
    properties = AttrField("properties")
    id = AttrField("id")


class Spine(XMLElement, tag="spine", ns=XMLNamespace.OPF):
    id = AttrField("id")
    toc = AttrField("toc")
    page_progression_direction = AttrField("page-progression-direction")
    page_map = AttrField("page-map")

    itemrefs = ChildListField(SpineItemRef)

    def add_itemref(self, idref: str, linear: str | None = None, **kwargs) -> SpineItemRef:
        new_ref = SpineItemRef.create(idref=idref, linear=linear, **kwargs)
        self.itemrefs = self.itemrefs + [new_ref]
        return new_ref

    def remove_itemref(self, itemref: SpineItemRef | None = None, idref: str | None = None):
        """Remove a spine itemref by its idref or object reference."""
        if itemref is not None:
            self.itemrefs = [r for r in self.itemrefs if r._elem is not itemref._elem]
        elif idref is not None:
            self.itemrefs = [r for r in self.itemrefs if r.idref != idref]


# ---------------------------------------------------------------------------
# Guide
# ---------------------------------------------------------------------------


class GuideReference(XMLElement, tag="reference", ns=XMLNamespace.OPF):
    type = AttrField("type")
    title = AttrField("title")
    href = AttrField("href")


class Guide(XMLElement, tag="guide", ns=XMLNamespace.OPF):
    references = ChildListField(GuideReference)

    def add_reference(self, type: str, href: str, title: str | None = None, **kwargs) -> GuideReference:
        new_ref = GuideReference.create(type=type, href=href, title=title, **kwargs)
        self.references = self.references + [new_ref]
        return new_ref

    def remove_reference(self, reference: GuideReference | None = None, type: str | None = None):
        """Remove a guide reference by its type or object reference."""
        if reference is not None:
            self.references = [r for r in self.references if r._elem is not reference._elem]
        elif type is not None:
            self.references = [r for r in self.references if r.type != type]


# ---------------------------------------------------------------------------
# Tours
# ---------------------------------------------------------------------------


class Tour(XMLElement, tag="tour", ns=XMLNamespace.OPF):
    id = AttrField("id")
    title = AttrField("title")


class Tours(XMLElement, tag="tours", ns=XMLNamespace.OPF):
    tours = ChildListField(Tour)

    def add_tour(self, id: str, title: str, **kwargs) -> Tour:
        new_tour = Tour.create(id=id, title=title, **kwargs)
        self.tours = self.tours + [new_tour]
        return new_tour

    def remove_tour(self, tour: Tour | None = None, id: str | None = None):
        """Remove a tour by its id or object reference."""
        if tour is not None:
            self.tours = [t for t in self.tours if t._elem is not tour._elem]
        elif id is not None:
            self.tours = [t for t in self.tours if t.id != id]


# ---------------------------------------------------------------------------
# PackageDocument
# ---------------------------------------------------------------------------


class PackageDocument(XMLDocumentSchema, tag="package", ns=XMLNamespace.OPF, nsmap=OPF_NSMAP):
    version = AttrField("version")
    unique_identifier = AttrField("unique-identifier")
    id = AttrField("id")
    prefix = AttrField("prefix")
    lang = AttrField("lang", ns=XMLNamespace.XML)
    dir = AttrField("dir")

    metadata = ChildField(Metadata)
    manifest = ChildField(Manifest)
    spine = ChildField(Spine)
    guide = ChildField(Guide, default=None)
    tours = ChildField(Tours, default=None)

    __unordered_tags__ = {"package", "metadata", "manifest", "guide", "tours"}
