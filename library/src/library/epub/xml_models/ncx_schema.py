"""
NCXDocument — descriptor-based model for EPUB NCX files.
Mirrors xml_pydantic/ncx_document.py without pydantic-xml.
"""

from library.epub.epub_namespaces import XMLNamespace
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, ChildField, ChildListField, ChildTextField


# ---------------------------------------------------------------------------
# Class Definitions (Structural Shells)
# ---------------------------------------------------------------------------


class Meta(XMLElement, tag="meta", ns=XMLNamespace.NCX): ...


class Head(XMLElement, tag="head", ns=XMLNamespace.NCX): ...


class TextElement(XMLElement, ns=XMLNamespace.NCX):
    """Wraps elements like <navLabel> or <docTitle> that contain a <text> child."""

    ...


class Content(XMLElement, tag="content", ns=XMLNamespace.NCX): ...


class NavPoint(XMLElement, tag="navPoint", ns=XMLNamespace.NCX):
    def add_nav_point(self, content: "Content", id: str | None = None, **kwargs) -> "NavPoint":
        new_point = NavPoint.create(content=content, id=id, **kwargs)
        self.nav_points = self.nav_points + [new_point]
        return new_point

    def remove_nav_point(self, point: "NavPoint | None" = None, id: str | None = None):
        if point is not None:
            self.nav_points = [p for p in self.nav_points if p._elem is not point._elem]
        elif id is not None:
            self.nav_points = [p for p in self.nav_points if p.id != id]


class NavMap(XMLElement, tag="navMap", ns=XMLNamespace.NCX):
    def add_nav_point(self, content: "Content", id: str | None = None, **kwargs) -> "NavPoint":
        new_point = NavPoint.create(content=content, id=id, **kwargs)
        self.nav_points = self.nav_points + [new_point]
        return new_point

    def remove_nav_point(self, point: "NavPoint | None" = None, id: str | None = None):
        if point is not None:
            self.nav_points = [p for p in self.nav_points if p._elem is not point._elem]
        elif id is not None:
            self.nav_points = [p for p in self.nav_points if p.id != id]


class PageTarget(XMLElement, tag="pageTarget", ns=XMLNamespace.NCX): ...


class PageList(XMLElement, tag="pageList", ns=XMLNamespace.NCX):
    def add_page_target(
        self, content: "Content", id: str | None = None, value: str | None = None, type: str | None = None, **kwargs
    ) -> "PageTarget":
        new_target = PageTarget.create(content=content, id=id, value=value, type=type, **kwargs)
        self.page_targets = self.page_targets + [new_target]
        return new_target

    def remove_page_target(self, target: "PageTarget | None" = None, id: str | None = None):
        if target is not None:
            self.page_targets = [t for t in self.page_targets if t._elem is not target._elem]
        elif id is not None:
            self.page_targets = [t for t in self.page_targets if t.id != id]


class NavTarget(XMLElement, tag="navTarget", ns=XMLNamespace.NCX): ...


class NavList(XMLElement, tag="navList", ns=XMLNamespace.NCX):
    def add_nav_target(self, content: "Content", id: str, **kwargs) -> "NavTarget":
        new_target = NavTarget.create(content=content, id=id, **kwargs)
        self.nav_targets = self.nav_targets + [new_target]
        return new_target

    def remove_nav_target(self, target: "NavTarget | None" = None, id: str | None = None):
        if target is not None:
            self.nav_targets = [t for t in self.nav_targets if t._elem is not target._elem]
        elif id is not None:
            self.nav_targets = [t for t in self.nav_targets if t.id != id]


class NCXDocument(XMLDocumentSchema, tag="ncx", ns=XMLNamespace.NCX):
    __unordered_tags__ = {"head", "ncx"}


# ---------------------------------------------------------------------------
# Schema Mapping (Descriptors assigned post-definition)
# ---------------------------------------------------------------------------

# Meta / Head
Meta.name = AttrField("name")
Meta.content = AttrField("content")
Meta.scheme = AttrField("scheme")

Head.metas = ChildListField(Meta)

# Text / Content
TextElement.text = ChildTextField("text", ns=XMLNamespace.NCX)

Content.src = AttrField("src")

# NavPoint
NavPoint.id = AttrField("id")
NavPoint.class_attr = AttrField("class")
NavPoint.play_order = AttrField("playOrder", type=int)
NavPoint.nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
NavPoint.content = ChildField(Content, default=None)
NavPoint.nav_points = ChildListField(NavPoint, tag="navPoint")

# NavMap
NavMap.nav_infos = ChildListField(TextElement, tag="navInfo")
NavMap.nav_points = ChildListField(NavPoint, tag="navPoint")

# PageList / PageTarget
PageTarget.id = AttrField("id")
PageTarget.value = AttrField("value")
PageTarget.type = AttrField("type")
PageTarget.class_attr = AttrField("class")
PageTarget.play_order = AttrField("playOrder", type=int)
PageTarget.nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
PageTarget.content = ChildField(Content, default=None)

PageList.id = AttrField("id")
PageList.class_attr = AttrField("class")
PageList.nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
PageList.nav_infos = ChildListField(TextElement, tag="navInfo")
PageList.page_targets = ChildListField(PageTarget, tag="pageTarget")

# NavList / NavTarget
NavTarget.id = AttrField("id")
NavTarget.class_attr = AttrField("class")
NavTarget.value = AttrField("value")
NavTarget.play_order = AttrField("playOrder", type=int)
NavTarget.nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
NavTarget.content = ChildField(Content, default=None)

NavList.id = AttrField("id")
NavList.class_attr = AttrField("class")
NavList.nav_label = ChildField(TextElement, tag="navLabel", ns=XMLNamespace.NCX, default=None)
NavList.nav_infos = ChildListField(TextElement, tag="navInfo")
NavList.nav_targets = ChildListField(NavTarget, tag="navTarget")

# NCXDocument
NCXDocument.version = AttrField("version")
NCXDocument.xml_lang = AttrField("lang", ns=XMLNamespace.XML)
NCXDocument.dir = AttrField("dir")
NCXDocument.head = ChildField(Head)
NCXDocument.nav_map = ChildField(NavMap, tag="navMap", ns=XMLNamespace.NCX)
NCXDocument.page_list = ChildField(PageList, tag="pageList", ns=XMLNamespace.NCX, default=None)
NCXDocument.doc_title = ChildField(TextElement, tag="docTitle")
NCXDocument.doc_authors = ChildListField(TextElement, tag="docAuthor")
NCXDocument.nav_lists = ChildListField(NavList, tag="navList")
