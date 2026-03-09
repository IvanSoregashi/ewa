"""
PackageDocument — descriptor-based model for EPUB OPF files.
Mirrors xml_pydantic/package_document.py without pydantic-xml.
"""

from library.epub.constants import DC_NS, XML_NS, XSI_NS, OPF_NS, OPF_NSMAP
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, TextField, ChildField, ChildListField


# ---------------------------------------------------------------------------
# Metadata elements
# ---------------------------------------------------------------------------


class DCElement(XMLElement):
    """Base for Dublin Core elements — lives in dc: namespace."""

    __ns__ = DC_NS

    id = AttrField("id")
    xml_lang = AttrField("lang", ns=XML_NS)
    xsi_type = AttrField("type", ns=XSI_NS)

    file_as = AttrField("file-as")
    file_as_ns = AttrField("file-as", ns=OPF_NS)
    role = AttrField("role")
    role_ns = AttrField("role", ns=OPF_NS)
    scheme = AttrField("scheme")
    scheme_ns = AttrField("scheme", ns=OPF_NS)
    event = AttrField("event")
    event_ns = AttrField("event", ns=OPF_NS)

    name = AttrField("name")
    content_attr = AttrField("content")

    text = TextField()


class DCMeta(DCElement):
    """<meta> in the dc/opf namespace (old EPUB 2 style)."""

    __tag__ = "meta"
    __ns__ = DC_NS


class Meta(DCElement):
    """<meta> in the opf namespace (EPUB 3 style)."""

    __tag__ = "meta"
    __ns__ = OPF_NS

    property = AttrField("property")
    refines = AttrField("refines")


class Metadata(XMLElement):
    __tag__ = "metadata"
    __ns__ = OPF_NS

    @staticmethod
    def _find_all(elem, tag, ns):
        clark = f"{{{ns}}}{tag}" if ns else tag
        return elem.findall(clark)

    def _get_dc_list(self, tag):
        return [DCElement(e) for e in self._find_all(self._elem, tag, DC_NS)]

    @property
    def titles(self):
        return self._get_dc_list("title")

    @property
    def creators(self):
        return self._get_dc_list("creator")

    @property
    def subjects(self):
        return self._get_dc_list("subject")

    @property
    def descriptions(self):
        return self._get_dc_list("description")

    @property
    def publishers(self):
        return self._get_dc_list("publisher")

    @property
    def contributors(self):
        return self._get_dc_list("contributor")

    @property
    def dates(self):
        return self._get_dc_list("date")

    @property
    def types(self):
        return self._get_dc_list("type")

    @property
    def formats(self):
        return self._get_dc_list("format")

    @property
    def identifiers(self):
        return self._get_dc_list("identifier")

    @property
    def sources(self):
        return self._get_dc_list("source")

    @property
    def languages(self):
        return self._get_dc_list("language")

    @property
    def relations(self):
        return self._get_dc_list("relation")

    @property
    def coverages(self):
        return self._get_dc_list("coverage")

    @property
    def rights(self):
        return self._get_dc_list("rights")

    @property
    def metas(self):
        return [Meta(e) for e in self._find_all(self._elem, "meta", OPF_NS)]

    @property
    def dc_metas(self):
        return [DCMeta(e) for e in self._find_all(self._elem, "meta", DC_NS)]

    @property
    def title(self) -> DCElement:
        return self.titles[0] if self.titles else None

    @property
    def language(self) -> DCElement:
        return self.languages[0] if self.languages else None


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class ManifestItem(XMLElement):
    __tag__ = "item"
    __ns__ = OPF_NS

    id = AttrField("id")
    href = AttrField("href")
    media_type = AttrField("media-type")
    properties = AttrField("properties")
    fallback = AttrField("fallback")
    overlay = AttrField("overlay")


class Manifest(XMLElement):
    __tag__ = "manifest"
    __ns__ = OPF_NS

    items = ChildListField(ManifestItem)


# ---------------------------------------------------------------------------
# Spine
# ---------------------------------------------------------------------------


class SpineItemRef(XMLElement):
    __tag__ = "itemref"
    __ns__ = OPF_NS

    idref = AttrField("idref")
    linear = AttrField("linear")
    properties = AttrField("properties")
    id = AttrField("id")


class Spine(XMLElement):
    __tag__ = "spine"
    __ns__ = OPF_NS

    id = AttrField("id")
    toc = AttrField("toc")
    page_progression_direction = AttrField("page-progression-direction")
    page_map = AttrField("page-map")

    itemrefs = ChildListField(SpineItemRef)


# ---------------------------------------------------------------------------
# Guide
# ---------------------------------------------------------------------------


class GuideReference(XMLElement):
    __tag__ = "reference"
    __ns__ = OPF_NS

    type = AttrField("type")
    title = AttrField("title")
    href = AttrField("href")


class Guide(XMLElement):
    __tag__ = "guide"
    __ns__ = OPF_NS

    references = ChildListField(GuideReference)


# ---------------------------------------------------------------------------
# Tours
# ---------------------------------------------------------------------------


class Tour(XMLElement):
    __tag__ = "tour"
    __ns__ = OPF_NS

    id = AttrField("id")
    title = AttrField("title")


class Tours(XMLElement):
    __tag__ = "tours"
    __ns__ = OPF_NS

    tours = ChildListField(Tour)


# ---------------------------------------------------------------------------
# PackageDocument
# ---------------------------------------------------------------------------


class PackageDocument(XMLDocumentSchema):
    __tag__ = "package"
    __ns__ = OPF_NS
    __nsmap__ = OPF_NSMAP

    version = AttrField("version")
    unique_identifier = AttrField("unique-identifier")
    id = AttrField("id")
    prefix = AttrField("prefix")
    xml_lang = AttrField("lang", ns=XML_NS)
    dir = AttrField("dir")

    metadata = ChildField(Metadata)
    manifest = ChildField(Manifest)
    spine = ChildField(Spine)
    guide = ChildField(Guide, default=None)
    tours = ChildField(Tours, default=None)

    __unordered_tags__ = {"package", "metadata", "manifest", "guide", "tours"}
