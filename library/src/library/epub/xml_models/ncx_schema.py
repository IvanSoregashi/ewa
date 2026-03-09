"""
NCXDocument — descriptor-based model for EPUB NCX files.
Mirrors xml_pydantic/ncx_document.py without pydantic-xml.
"""

from library.epub.epub_namespaces import XMLNamespace
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, ChildField, ChildListField, ChildTextField


# ---------------------------------------------------------------------------
# Head
# ---------------------------------------------------------------------------


class Meta(XMLElement, tag="meta", ns=XMLNamespace.NCX):
    name = AttrField("name")
    content = AttrField("content")
    scheme = AttrField("scheme")


class Head(XMLElement, tag="head", ns=XMLNamespace.NCX):
    metas = ChildListField(Meta)


# ---------------------------------------------------------------------------
# Shared sub-elements
# ---------------------------------------------------------------------------


class TextElement(XMLElement, ns=XMLNamespace.NCX):
    """Wraps elements like <navLabel> or <docTitle> that contain a <text> child."""

    text = ChildTextField("text", ns=XMLNamespace.NCX)


class Content(XMLElement, tag="content", ns=XMLNamespace.NCX):
    src = AttrField("src")


# ---------------------------------------------------------------------------
# NavPoint (recursive)
# ---------------------------------------------------------------------------


class NavPoint(XMLElement, tag="navPoint", ns=XMLNamespace.NCX):
    id = AttrField("id")
    class_attr = AttrField("class")
    play_order = AttrField("playOrder", type=int)

    nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
    content = ChildField(Content, default=None)

    @property
    def nav_points(self):
        clark = f"{{{XMLNamespace.NCX}}}navPoint"
        return [NavPoint(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# NavMap
# ---------------------------------------------------------------------------


class NavMap(XMLElement, tag="navMap", ns=XMLNamespace.NCX):
    @property
    def nav_infos(self):
        clark = f"{{{XMLNamespace.NCX}}}navInfo"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def nav_points(self):
        clark = f"{{{XMLNamespace.NCX}}}navPoint"
        return [NavPoint(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# PageList / PageTarget
# ---------------------------------------------------------------------------


class PageTarget(XMLElement, tag="pageTarget", ns=XMLNamespace.NCX):
    id = AttrField("id")
    value = AttrField("value")
    type = AttrField("type")
    class_attr = AttrField("class")
    play_order = AttrField("playOrder", type=int)

    nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
    content = ChildField(Content, default=None)


class PageList(XMLElement, tag="pageList", ns=XMLNamespace.NCX):
    id = AttrField("id")
    class_attr = AttrField("class")

    nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)

    @property
    def nav_infos(self):
        clark = f"{{{XMLNamespace.NCX}}}navInfo"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def page_targets(self):
        clark = f"{{{XMLNamespace.NCX}}}pageTarget"
        return [PageTarget(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# NavList / NavTarget
# ---------------------------------------------------------------------------


class NavTarget(XMLElement, tag="navTarget", ns=XMLNamespace.NCX):
    id = AttrField("id")
    class_attr = AttrField("class")
    value = AttrField("value")
    play_order = AttrField("playOrder", type=int)

    nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
    content = ChildField(Content, default=None)


class NavList(XMLElement, tag="navList", ns=XMLNamespace.NCX):
    id = AttrField("id")
    class_attr = AttrField("class")

    nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)

    @property
    def nav_infos(self):
        clark = f"{{{XMLNamespace.NCX}}}navInfo"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def nav_targets(self):
        clark = f"{{{XMLNamespace.NCX}}}navTarget"
        return [NavTarget(e) for e in self._elem.findall(clark)]


# ---------------------------------------------------------------------------
# NCXDocument
# ---------------------------------------------------------------------------


class NCXDocument(XMLDocumentSchema, tag="ncx", ns=XMLNamespace.NCX):
    version = AttrField("version")
    xml_lang = AttrField("lang", ns=XMLNamespace.XML)
    dir = AttrField("dir")

    head = ChildField(Head)
    nav_map = ChildField(NavMap, tag="navMap", ns=XMLNamespace.NCX)
    page_list = ChildField(PageList, tag="pageList", ns=XMLNamespace.NCX, default=None)

    @property
    def doc_title(self):
        clark = f"{{{XMLNamespace.NCX}}}docTitle"
        e = self._elem.find(clark)
        return TextElement(e) if e is not None else None

    @property
    def doc_authors(self):
        clark = f"{{{XMLNamespace.NCX}}}docAuthor"
        return [TextElement(e) for e in self._elem.findall(clark)]

    @property
    def nav_lists(self):
        clark = f"{{{XMLNamespace.NCX}}}navList"
        return [NavList(e) for e in self._elem.findall(clark)]

    __unordered_tags__ = {"head", "ncx"}
