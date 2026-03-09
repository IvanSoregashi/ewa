"""
NavDocument — descriptor-based model for EPUB Navigation Documents (XHTML nav files).
Mirrors xml_pydantic/nav_document.py without pydantic-xml.
"""

from library.epub.epub_namespaces import NamespacePrefix, XMLNamespace
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, TextField, ChildField, ChildListField, ChildTextField


# ---------------------------------------------------------------------------
# Class Definitions (Structural Shells)
# ---------------------------------------------------------------------------


class CommonAttributes(XMLElement, ns=XMLNamespace.XHTML):
    """Base that many nav elements share."""

    ...


class NavInline(CommonAttributes, tag=""): ...


class NavHeading(NavInline, tag=""): ...


class NavLink(NavInline, tag="a"): ...


class NavListItem(CommonAttributes, tag="li"): ...


class NavList(CommonAttributes, tag="ol"):
    def add_item(
        self, link: "NavLink | None" = None, span: "NavInline | None" = None, ol: "NavList | None" = None, **kwargs
    ) -> "NavListItem":
        new_item = NavListItem.create(a=link, span=span, ol=ol, **kwargs)
        self.items = self.items + [new_item]
        return new_item

    def remove_item(self, item: "NavListItem | None" = None, id: str | None = None):
        """Remove a nav list item by its id or object reference."""
        if item is not None:
            self.items = [i for i in self.items if i._elem is not item._elem]
        elif id is not None:
            self.items = [i for i in self.items if i.id != id]


class NavElement(CommonAttributes, tag="nav"): ...


class BlockElement(CommonAttributes):
    @property
    def nav(self):
        return self.nav_navs[0] if hasattr(self, "nav_navs") and self.nav_navs else None


class Div(BlockElement, tag="div"): ...


class Section(BlockElement, tag="section"): ...


class Article(BlockElement, tag="article"): ...


class Header(BlockElement, tag="header"): ...


class Footer(BlockElement, tag="footer"): ...


class Body(BlockElement, tag="body"): ...


class HeadLink(CommonAttributes, tag="link"): ...


class HeadMeta(XMLElement, tag="meta", ns=XMLNamespace.XHTML): ...


class HeadStyle(XMLElement, tag="style", ns=XMLNamespace.XHTML): ...


class Head(CommonAttributes, tag="head"): ...


class NavDocument(XMLDocumentSchema, tag="html", ns=XMLNamespace.XHTML):
    __unordered_tags__ = {
        "html",
        "head",
        "body",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "aside",
        "nav",
        "li",
    }
    __ignore_xmlns__ = True


# ---------------------------------------------------------------------------
# Schema Mapping (Descriptors assigned post-definition)
# ---------------------------------------------------------------------------

# CommonAttributes
CommonAttributes.id = AttrField("id")
CommonAttributes.class_attr = AttrField("class")
CommonAttributes.style = AttrField("style")
CommonAttributes.lang = AttrField("lang")
CommonAttributes.xml_lang = AttrField("lang", ns=NamespacePrefix.XML)
CommonAttributes.dir = AttrField("dir")
CommonAttributes.hidden = AttrField("hidden")
CommonAttributes.epub_type = AttrField("type", ns=XMLNamespace.EPUB)
CommonAttributes.epub_prefix = AttrField("prefix", ns=XMLNamespace.EPUB)
CommonAttributes.role = AttrField("role")
CommonAttributes.value = AttrField("value")
CommonAttributes.data_type = AttrField("data-type")
CommonAttributes.text = TextField()

# NavLink
NavLink.href = AttrField("href")

# NavListItem
NavListItem.a = ChildField(NavLink, tag="a")
NavListItem.span = ChildField(NavInline, tag="span")
NavListItem.ol = ChildField(NavList, tag="ol")

# NavList
NavList.items = ChildListField(NavListItem)

# NavElement
NavElement.h1 = ChildField(NavHeading, tag="h1")
NavElement.h2 = ChildField(NavHeading, tag="h2")
NavElement.h3 = ChildField(NavHeading, tag="h3")
NavElement.ol = ChildField(NavList)

# BlockElement
BlockElement.h1s = ChildListField(NavHeading, tag="h1")
BlockElement.h3s = ChildListField(NavHeading, tag="h3")
BlockElement.ps = ChildListField(NavInline, tag="p")
BlockElement.nav_navs = ChildListField(NavElement, tag="nav")
BlockElement.divs = ChildListField(Div, tag="div")
BlockElement.sections = ChildListField(Section, tag="section")
BlockElement.article = ChildField(Article, tag="article")
BlockElement.header = ChildField(Header, tag="header")
BlockElement.footer = ChildField(Footer, tag="footer")

# Head sub-elements
HeadLink.href = AttrField("href")
HeadLink.rel = AttrField("rel")
HeadLink.type = AttrField("type")

HeadMeta.charset = AttrField("charset")
HeadMeta.content = AttrField("content")
HeadMeta.http_equiv = AttrField("http-equiv")
HeadMeta.name = AttrField("name")

HeadStyle.type = AttrField("type")
HeadStyle.text = TextField()

# Head
Head.title = ChildTextField("title", ns=XMLNamespace.XHTML)
Head.metas = ChildListField(HeadMeta)
Head.links = ChildListField(HeadLink)
Head.styles = ChildListField(HeadStyle)

# NavDocument
NavDocument.id = AttrField("id")
NavDocument.class_attr = AttrField("class")
NavDocument.style = AttrField("style")
NavDocument.lang = AttrField("lang")
NavDocument.xml_lang = AttrField("lang", ns=NamespacePrefix.XML)
NavDocument.dir = AttrField("dir")
NavDocument.hidden = AttrField("hidden")
NavDocument.epub_type = AttrField("type", ns=XMLNamespace.EPUB)
NavDocument.epub_prefix = AttrField("prefix", ns=XMLNamespace.EPUB)
NavDocument.prefix = AttrField("prefix")
NavDocument.head = ChildField(Head)
NavDocument.body = ChildField(Body)

# Inline circular references
NavInline.spans = ChildListField(NavInline, tag="span")
NavInline.is_ = ChildListField(NavInline, tag="i")
NavInline.bs = ChildListField(NavInline, tag="b")
NavInline.ems = ChildListField(NavInline, tag="em")
NavInline.codes = ChildListField(NavInline, tag="code")
NavInline.vars = ChildListField(NavInline, tag="var")
NavInline.as_ = ChildListField(NavLink, tag="a")
