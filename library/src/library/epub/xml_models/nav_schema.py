"""
NavDocument — descriptor-based model for EPUB Navigation Documents (XHTML nav files).
Mirrors xml_pydantic/nav_document.py without pydantic-xml.
"""
from library.epub.epub_namespaces import XHTML_NS, EPUB_NS, XML_NS
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

class CommonAttributes(XMLElement):
    """Base that many nav elements share."""
    __ns__ = XHTML_NS

    id          = AttrField("id")
    class_attr  = AttrField("class")
    style       = AttrField("style")
    lang        = AttrField("lang")
    xml_lang    = AttrField("lang",   ns=XML_NS)
    dir         = AttrField("dir")
    hidden      = AttrField("hidden")
    epub_type   = AttrField("type",   ns=EPUB_NS)
    epub_prefix = AttrField("prefix", ns=EPUB_NS)
    role        = AttrField("role")
    value       = AttrField("value")
    text        = TextField()


# ---------------------------------------------------------------------------
# Inline elements (NavInline, NavLink, NavHeading)
# These can be nested, so we use dynamic properties.
# ---------------------------------------------------------------------------

class NavInline(CommonAttributes):
    __tag__ = ""  # no fixed tag — used generically
    __ns__  = XHTML_NS

    @property
    def spans(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "span", XHTML_NS)]

    @property
    def is_(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "i", XHTML_NS)]

    @property
    def bs(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "b", XHTML_NS)]

    @property
    def ems(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "em", XHTML_NS)]

    @property
    def codes(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "code", XHTML_NS)]

    @property
    def vars(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "var", XHTML_NS)]

    @property
    def as_(self):
        return [NavLink(e) for e in _find_all_direct(self._elem, "a", XHTML_NS)]


class NavLink(NavInline):
    __tag__ = "a"
    __ns__  = XHTML_NS

    href = AttrField("href")


class NavHeading(NavInline):
    __tag__ = ""
    __ns__  = XHTML_NS


# ---------------------------------------------------------------------------
# NavListItem / NavList (ol > li > a/span + nested ol)
# ---------------------------------------------------------------------------

class NavListItem(CommonAttributes):
    __tag__ = "li"
    __ns__  = XHTML_NS

    @property
    def link(self):
        e = _find_first(self._elem, "a", XHTML_NS)
        return NavLink(e) if e is not None else None

    @property
    def a(self):
        return self.link

    @property
    def span(self):
        e = _find_first(self._elem, "span", XHTML_NS)
        return NavInline(e) if e is not None else None

    @property
    def ol(self):
        e = _find_first(self._elem, "ol", XHTML_NS)
        return NavList(e) if e is not None else None


class NavList(CommonAttributes):
    __tag__ = "ol"
    __ns__  = XHTML_NS

    @property
    def items(self):
        return [NavListItem(e) for e in _find_all_direct(self._elem, "li", XHTML_NS)]


# ---------------------------------------------------------------------------
# NavElement  (<nav>)
# ---------------------------------------------------------------------------

class NavElement(CommonAttributes):
    __tag__ = "nav"
    __ns__  = XHTML_NS

    @property
    def h1(self):
        e = _find_first(self._elem, "h1", XHTML_NS)
        return NavHeading(e) if e is not None else None

    @property
    def h2(self):
        e = _find_first(self._elem, "h2", XHTML_NS)
        return NavHeading(e) if e is not None else None

    @property
    def h3(self):
        e = _find_first(self._elem, "h3", XHTML_NS)
        return NavHeading(e) if e is not None else None

    @property
    def ol(self):
        e = _find_first(self._elem, "ol", XHTML_NS)
        return NavList(e) if e is not None else None


# ---------------------------------------------------------------------------
# Block-level elements  (div, section, article, header, footer, body)
# All share the same structural property set — extracted as a mixin.
# ---------------------------------------------------------------------------

class BlockElement(CommonAttributes):
    __ns__ = XHTML_NS

    @property
    def h1s(self):
        return [NavHeading(e) for e in _find_all_direct(self._elem, "h1", XHTML_NS)]

    @property
    def h3s(self):
        return [NavHeading(e) for e in _find_all_direct(self._elem, "h3", XHTML_NS)]

    @property
    def ps(self):
        return [NavInline(e) for e in _find_all_direct(self._elem, "p", XHTML_NS)]

    @property
    def divs(self):
        return [Div(e) for e in _find_all_direct(self._elem, "div", XHTML_NS)]

    @property
    def navs(self):
        return [NavElement(e) for e in _find_all_direct(self._elem, "nav", XHTML_NS)]

    @property
    def sections(self):
        return [Section(e) for e in _find_all_direct(self._elem, "section", XHTML_NS)]

    @property
    def article(self):
        e = _find_first(self._elem, "article", XHTML_NS)
        return Article(e) if e is not None else None

    @property
    def header(self):
        e = _find_first(self._elem, "header", XHTML_NS)
        return Header(e) if e is not None else None

    @property
    def footer(self):
        e = _find_first(self._elem, "footer", XHTML_NS)
        return Footer(e) if e is not None else None

    @property
    def nav(self):
        return self.navs[0] if self.navs else None


class Div(BlockElement):
    __tag__ = "div"

class Section(BlockElement):
    __tag__ = "section"

class Article(BlockElement):
    __tag__ = "article"

class Header(BlockElement):
    __tag__ = "header"

class Footer(BlockElement):
    __tag__ = "footer"

class Body(BlockElement):
    __tag__ = "body"
    __ns__  = XHTML_NS


# ---------------------------------------------------------------------------
# Head sub-elements
# ---------------------------------------------------------------------------

class HeadLink(CommonAttributes):
    __tag__ = "link"
    __ns__  = XHTML_NS

    href = AttrField("href")
    rel  = AttrField("rel")
    type = AttrField("type")


class HeadMeta(XMLElement):
    __tag__ = "meta"
    __ns__  = XHTML_NS

    charset     = AttrField("charset")
    content     = AttrField("content")
    http_equiv  = AttrField("http-equiv")
    name        = AttrField("name")


class HeadStyle(XMLElement):
    __tag__ = "style"
    __ns__  = XHTML_NS

    type = AttrField("type")
    text = TextField()


class Head(CommonAttributes):
    __tag__ = "head"
    __ns__  = XHTML_NS

    @property
    def title(self):
        e = _find_first(self._elem, "title", XHTML_NS)
        return e.text if e is not None else None

    @property
    def metas(self):
        return [HeadMeta(e) for e in _find_all_direct(self._elem, "meta", XHTML_NS)]

    @property
    def links(self):
        return [HeadLink(e) for e in _find_all_direct(self._elem, "link", XHTML_NS)]

    @property
    def styles(self):
        return [HeadStyle(e) for e in _find_all_direct(self._elem, "style", XHTML_NS)]


# ---------------------------------------------------------------------------
# NavDocument  (<html>)
# ---------------------------------------------------------------------------

class NavDocument(XMLDocumentSchema):
    __tag__   = "html"
    __ns__    = XHTML_NS

    id          = AttrField("id")
    class_attr  = AttrField("class")
    style       = AttrField("style")
    lang        = AttrField("lang")
    xml_lang    = AttrField("lang",   ns=XML_NS)
    dir         = AttrField("dir")
    hidden      = AttrField("hidden")
    epub_type   = AttrField("type",   ns=EPUB_NS)
    epub_prefix = AttrField("prefix", ns=EPUB_NS)
    prefix      = AttrField("prefix")

    head = ChildField(Head)
    body = ChildField(Body)

    __unordered_tags__ = {
        "html", "head", "body", "div", "section",
        "article", "header", "footer", "aside", "nav", "li",
    }
    __ignore_xmlns__ = True
