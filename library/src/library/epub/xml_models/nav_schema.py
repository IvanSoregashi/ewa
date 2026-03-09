"""
NavDocument — descriptor-based model for EPUB Navigation Documents (XHTML nav files).
Mirrors xml_pydantic/nav_document.py without pydantic-xml.
"""
from library.epub.epub_namespaces import NamespacePrefix, XMLNamespace
from library.xml.document_custom import XMLDocumentSchema, XMLElement
from library.xml.descriptor_fields import AttrField, TextField, ChildField


def _find_all_direct(elem, tag, ns):
    """Find all direct children with Clark-notation tag."""
    clark = f"{{{ns}}}{tag}" if ns else tag
    return [c for c in elem if c.tag == clark]


def _find_first(elem, tag, ns):
    clark = f"{{{ns}}}{tag}" if ns else tag
    return elem.find(clark)


# ---------------------------------------------------------------------------
# common attributes mixin (via regular fields — works because we don't have
# lxml elements during class definition, only during __get__ at runtime)
# ---------------------------------------------------------------------------

class CommonAttributes(XMLElement, ns=XMLNamespace.XHTML):
    """Base that many nav elements share."""

    id          = AttrField("id")
    class_attr  = AttrField("class")
    style       = AttrField("style")
    lang        = AttrField("lang")
    xml_lang    = AttrField("lang",   ns=XMLNamespace.XML)
    dir         = AttrField("dir")
    hidden      = AttrField("hidden")
    epub_type   = AttrField("type",   ns=NamespacePrefix.EPUB)
    epub_prefix = AttrField("prefix", ns=NamespacePrefix.EPUB)
    role        = AttrField("role")
    value       = AttrField("value")
    text        = TextField()


# ---------------------------------------------------------------------------
# Inline elements (NavInline, NavLink, NavHeading)
# These can be nested, so we use dynamic properties.
# ---------------------------------------------------------------------------

class NavInline(CommonAttributes, tag=""):

    @property
    def spans(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "span", XMLNamespace.XHTML)]

    @property
    def is_(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "i", XMLNamespace.XHTML)]

    @property
    def bs(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "b", XMLNamespace.XHTML)]

    @property
    def ems(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "em", XMLNamespace.XHTML)]

    @property
    def codes(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "code", XMLNamespace.XHTML)]

    @property
    def vars(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "var", XMLNamespace.XHTML)]

    @property
    def as_(self):
        return [NavLink(e) for e in _find_all_direct(self._elem, "a", XMLNamespace.XHTML)]


class NavHeading(NavInline, tag=""): ...

class NavLink(NavInline, tag="a"):
    href = AttrField("href")




# ---------------------------------------------------------------------------
# NavListItem / NavList (ol > li > a/span + nested ol)
# ---------------------------------------------------------------------------

class NavListItem(CommonAttributes, tag="li"):

    @property
    def link(self):
        e = _find_first(self._elem, "a", XMLNamespace.XHTML)
        return NavLink(e) if e is not None else None

    @property
    def a(self):
        return self.link

    @property
    def span(self):
        e = _find_first(self._elem, "span", XMLNamespace.XHTML)
        return NavInline(e) if e is not None else None

    @property
    def ol(self):
        e = _find_first(self._elem, "ol", XMLNamespace.XHTML)
        return NavList(e) if e is not None else None


class NavList(CommonAttributes, tag="ol"):

    @property
    def items(self):
        return [NavListItem(e) for e in _find_all_direct(self._elem, "li", XMLNamespace.XHTML)]


# ---------------------------------------------------------------------------
# NavElement  (<nav>)
# ---------------------------------------------------------------------------

class NavElement(CommonAttributes, tag="nav"):

    @property
    def h1(self):
        e = _find_first(self._elem, "h1", XMLNamespace.XHTML)
        return NavHeading(e) if e is not None else None

    @property
    def h2(self):
        e = _find_first(self._elem, "h2", XMLNamespace.XHTML)
        return NavHeading(e) if e is not None else None

    @property
    def h3(self):
        e = _find_first(self._elem, "h3", XMLNamespace.XHTML)
        return NavHeading(e) if e is not None else None

    @property
    def ol(self):
        e = _find_first(self._elem, "ol", XMLNamespace.XHTML)
        return NavList(e) if e is not None else None


# ---------------------------------------------------------------------------
# Block-level elements  (div, section, article, header, footer, body)
# All share the same structural property set — extracted as a mixin.
# ---------------------------------------------------------------------------

class BlockElement(CommonAttributes):

    @property
    def h1s(self):
        return [NavHeading(e) for e in _find_all_direct(self._elem, "h1", XMLNamespace.XHTML)]

    @property
    def h3s(self):
        return [NavHeading(e) for e in _find_all_direct(self._elem, "h3", XMLNamespace.XHTML)]

    @property
    def ps(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "p", XMLNamespace.XHTML)]

    @property
    def divs(self):
        return [Div(e) for e in _find_all_direct(self._elem, "div", XMLNamespace.XHTML)]

    @property
    def navs(self):
        return [NavElement(e) for e in _find_all_direct(self._elem, "nav", XMLNamespace.XHTML)]

    @property
    def sections(self):
        return [Section(e) for e in _find_all_direct(self._elem, "section", XMLNamespace.XHTML)]

    @property
    def article(self):
        e = _find_first(self._elem, "article", XMLNamespace.XHTML)
        return Article(e) if e is not None else None

    @property
    def header(self):
        e = _find_first(self._elem, "header", XMLNamespace.XHTML)
        return Header(e) if e is not None else None

    @property
    def footer(self):
        e = _find_first(self._elem, "footer", XMLNamespace.XHTML)
        return Footer(e) if e is not None else None

    @property
    def nav(self):
        return self.navs[0] if self.navs else None


class Div(BlockElement, tag="div"): ...
class Section(BlockElement, tag="section"): ...
class Article(BlockElement, tag="article"): ...
class Header(BlockElement, tag="header"): ...
class Footer(BlockElement, tag="footer"): ...
class Body(BlockElement, tag="body"): ...


# ---------------------------------------------------------------------------
# Head sub-elements
# ---------------------------------------------------------------------------

class HeadLink(CommonAttributes, tag="link"):
    href = AttrField("href")
    rel  = AttrField("rel")
    type = AttrField("type")


class HeadMeta(XMLElement, tag="meta", ns=XMLNamespace.XHTML):
    charset     = AttrField("charset")
    content     = AttrField("content")
    http_equiv  = AttrField("http-equiv")
    name        = AttrField("name")


class HeadStyle(XMLElement, tag="style", ns=XMLNamespace.XHTML):
    type = AttrField("type")
    text = TextField()


class Head(CommonAttributes, tag="head"):

    @property
    def title(self):
        e = _find_first(self._elem, "title", XMLNamespace.XHTML)
        return e.text if e is not None else None

    @property
    def metas(self):
        return [HeadMeta(e) for e in _find_all_direct(self._elem, "meta", XMLNamespace.XHTML)]

    @property
    def links(self):
        return [HeadLink(e) for e in _find_all_direct(self._elem, "link", XMLNamespace.XHTML)]

    @property
    def styles(self):
        return [HeadStyle(e) for e in _find_all_direct(self._elem, "style", XMLNamespace.XHTML)]


# ---------------------------------------------------------------------------
# NavDocument  (<html>)
# ---------------------------------------------------------------------------

class NavDocument(XMLDocumentSchema, tag="html", ns=XMLNamespace.XHTML):

    id          = AttrField("id")
    class_attr  = AttrField("class")
    style       = AttrField("style")
    lang        = AttrField("lang")
    xml_lang    = AttrField("lang",   ns=XMLNamespace.XML)
    dir         = AttrField("dir")
    hidden      = AttrField("hidden")
    epub_type   = AttrField("type",   ns=XMLNamespace.EPUB)
    epub_prefix = AttrField("prefix", ns=XMLNamespace.EPUB)
    prefix      = AttrField("prefix")

    head = ChildField(Head)
    body = ChildField(Body)

    __unordered_tags__ = {
        "html", "head", "body", "div", "section",
        "article", "header", "footer", "aside", "nav", "li",
    }
    __ignore_xmlns__ = True
