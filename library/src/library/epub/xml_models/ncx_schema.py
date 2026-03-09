"""
NCXDocument — descriptor-based model for EPUB NCX files.
Mirrors xml_pydantic/ncx_document.py without pydantic-xml.
"""
from library.epub.epub_namespaces import NCX_NS, XML_NS
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, ChildField, ChildListField, ChildTextField


# ---------------------------------------------------------------------------
# Head
# ---------------------------------------------------------------------------

class Meta(XMLElement):
    __tag__ = "meta"
    __ns__  = NCX_NS

    name    = AttrField("name")
    content = AttrField("content")
    scheme  = AttrField("scheme")


class Head(XMLElement):
    __tag__ = "head"
    __ns__  = NCX_NS

    metas = ChildListField(Meta)


# ---------------------------------------------------------------------------
# Shared sub-elements
# ---------------------------------------------------------------------------

class TextElement(XMLElement):
    """Wraps elements like <navLabel> or <docTitle> that contain a <text> child."""
    __ns__ = NCX_NS

    text = ChildTextField("text", ns=NCX_NS)


class Content(XMLElement):
    __tag__ = "content"
    __ns__  = NCX_NS

    src = AttrField("src")


# ---------------------------------------------------------------------------
# NavPoint (recursive)
# ---------------------------------------------------------------------------

class NavPoint(XMLElement):
    __tag__ = "navPoint"
    __ns__  = NCX_NS

    id          = AttrField("id")
    class_attr  = AttrField("class")
    play_order  = AttrField("playOrder", type=int)

    nav_label   = ChildField(TextElement, tag="navLabel", ns=NCX_NS, default=None)
    content     = ChildField(Content, default=None)

    @property
    def nav_points(self):
        clark = f"{{{NCX_NS}}}navPoint"
        return [NavPoint(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# NavMap
# ---------------------------------------------------------------------------

class NavMap(XMLElement):
    __tag__ = "navMap"
    __ns__  = NCX_NS

    @property
    def nav_infos(self):
        clark = f"{{{NCX_NS}}}navInfo"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def nav_points(self):
        clark = f"{{{NCX_NS}}}navPoint"
        return [NavPoint(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# PageList / PageTarget
# ---------------------------------------------------------------------------

class PageTarget(XMLElement):
    __tag__ = "pageTarget"
    __ns__  = NCX_NS

    id         = AttrField("id")
    value      = AttrField("value")
    type       = AttrField("type")
    class_attr = AttrField("class")
    play_order = AttrField("playOrder", type=int)

    nav_label  = ChildField(TextElement, tag="navLabel", ns=NCX_NS, default=None)
    content    = ChildField(Content, default=None)


class PageList(XMLElement):
    __tag__ = "pageList"
    __ns__  = NCX_NS

    id         = AttrField("id")
    class_attr = AttrField("class")

    nav_label    = ChildField(TextElement, tag="navLabel", ns=NCX_NS, default=None)

    @property
    def nav_infos(self):
        clark = f"{{{NCX_NS}}}navInfo"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def page_targets(self):
        clark = f"{{{NCX_NS}}}pageTarget"
        return [PageTarget(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# NavList / NavTarget
# ---------------------------------------------------------------------------

class NavTarget(XMLElement):
    __tag__ = "navTarget"
    __ns__  = NCX_NS

    id         = AttrField("id")
    class_attr = AttrField("class")
    value      = AttrField("value")
    play_order = AttrField("playOrder", type=int)

    nav_label  = ChildField(TextElement, tag="navLabel", ns=NCX_NS, default=None)
    content    = ChildField(Content, default=None)


class NavList(XMLElement):
    __tag__ = "navList"
    __ns__  = NCX_NS

    id         = AttrField("id")
    class_attr = AttrField("class")

    nav_label  = ChildField(TextElement, tag="navLabel", ns=NCX_NS, default=None)

    @property
    def nav_infos(self):
        clark = f"{{{NCX_NS}}}navInfo"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def nav_targets(self):
        clark = f"{{{NCX_NS}}}navTarget"
        return [NavTarget(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# NCXDocument
# ---------------------------------------------------------------------------

class NCXDocument(XMLDocumentSchema):
    __tag__ = "ncx"
    __ns__  = NCX_NS

    version  = AttrField("version")
    xml_lang = AttrField("lang", ns=XML_NS)
    dir      = AttrField("dir")

    head      = ChildField(Head)
    nav_map   = ChildField(NavMap, tag="navMap", ns=NCX_NS)
    page_list = ChildField(PageList, tag="pageList", ns=NCX_NS, default=None)

    @property
    def doc_title(self):
        clark = f"{{{NCX_NS}}}docTitle"
        e = self._elem.find(clark)
        return TextElement(e) if e is not None else None

    @property
    def doc_authors(self):
        clark = f"{{{NCX_NS}}}docAuthor"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def nav_lists(self):
        clark = f"{{{NCX_NS}}}navList"
        return [NavList(e) for e in self._elem.findall(clark)]

    __unordered_tags__ = {"head", "ncx"}
