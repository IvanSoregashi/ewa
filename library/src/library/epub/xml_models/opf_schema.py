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


class DCMeta(DCElement, tag="meta", ns=XMLNamespace.DC):
    """<meta> in the dc/opf namespace (old EPUB 2 style)."""


class Meta(DCElement, tag="meta", ns=XMLNamespace.OPF):
    """<meta> in the opf namespace (EPUB 3 style)."""

    property = AttrField("property")
    refines = AttrField("refines")


class Metadata(XMLElement, tag="metadata", ns=XMLNamespace.OPF):
    titles = ChildListField(DCElement, tag="title")
    creators = ChildListField(DCElement, tag="creator")
    subjects = ChildListField(DCElement, tag="subject")
    descriptions = ChildListField(DCElement, tag="description")
    publishers = ChildListField(DCElement, tag="publisher")
    contributors = ChildListField(DCElement, tag="contributor")
    dates = ChildListField(DCElement, tag="date")
    types = ChildListField(DCElement, tag="type")
    formats = ChildListField(DCElement, tag="format")
    identifiers = ChildListField(DCElement, tag="identifier")
    sources = ChildListField(DCElement, tag="source")
    languages = ChildListField(DCElement, tag="language")
    relations = ChildListField(DCElement, tag="relation")
    coverages = ChildListField(DCElement, tag="coverage")
    rights = ChildListField(DCElement, tag="rights")

    metas = ChildListField(Meta)  # default tag/ns from Meta
    dc_metas = ChildListField(DCMeta)  # default tag/ns from DCMeta

    @property
    def title(self) -> DCElement:
        return self.titles[0] if self.titles else None

    @property
    def language(self) -> DCElement:
        return self.languages[0] if self.languages else None

    def add_metadata(self, tag: str | DCMetadataType, text: str, dc: bool = True, **kwargs):
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


# ---------------------------------------------------------------------------
# Guide
# ---------------------------------------------------------------------------


class GuideReference(XMLElement, tag="reference", ns=XMLNamespace.OPF):
    type = AttrField("type")
    title = AttrField("title")
    href = AttrField("href")


class Guide(XMLElement, tag="guide", ns=XMLNamespace.OPF):
    references = ChildListField(GuideReference)


# ---------------------------------------------------------------------------
# Tours
# ---------------------------------------------------------------------------


class Tour(XMLElement, tag="tour", ns=XMLNamespace.OPF):
    id = AttrField("id")
    title = AttrField("title")


class Tours(XMLElement, tag="tours", ns=XMLNamespace.OPF):
    tours = ChildListField(Tour)


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
