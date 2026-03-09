from library.epub.epub_namespaces import NamespacePrefix
from pydantic_xml import BaseXmlModel, attr, element
from library.xml.document_pydantic import XMLDocumentModel
from library.epub.epub_namespaces import NAV_NSMAP




class CommonAttributes(BaseXmlModel, nsmap=NAV_NSMAP):
    id: str | None = attr(default=None)
    class_attr: str | None = attr(name="class", default=None)
    style: str | None = attr(default=None)  # 10+
    lang: str | None = attr(default=None)
    xml_lang: str | None = attr(name="lang", ns=NamespacePrefix.XML, default=None)
    dir: str | None = attr(default=None)  # 10+
    hidden: str | None = attr(default=None)
    epub_type: str | None = attr(name="type", ns=NamespacePrefix.EPUB, default=None)
    epub_prefix: str | None = attr(name="prefix", ns=NamespacePrefix.EPUB, default=None)
    role: str | None = attr(default=None)
    value: str | None = attr(default=None)  # 1 C:\Users\Ivan\.ewa\epub\nav\6bfb89338d0e7deef8bfddc973dc531c_toc.xhtml


class Inline(CommonAttributes):
    """Mixin to provide shared inline elements for NavInline, NavLink, and NavHeading."""
    spans: list[NavInline] = element(tag="span", default=[])  # 2
    is_: list[NavInline] = element(tag="i", default=[])  # 5
    bs: list[NavInline] = element(tag="b", default=[])  # 1
    ems: list[NavInline] = element(tag="em", default=[])  # 1
    codes: list[NavInline] = element(tag="code", default=[])  # 1
    vars: list[NavInline] = element(tag="var", default=[])  # 1
    as_: list[NavLink] = element(tag="a", default=[])  # 4 have links
    text: str | None = None


class NavInline(Inline): ...


class NavHeading(Inline): ...


class NavLink(Inline, tag="a"):
    href: str = attr()


class NavListItem(CommonAttributes, tag="li", search_mode="unordered"):
    link: NavLink | None = element(tag="a", default=None)
    span: NavInline | None = element(tag="span", default=None)
    ol: NavList | None = element(tag="ol", default=None)

    @property
    def a(self) -> NavLink | None:
        return self.link


class NavList(CommonAttributes, tag="ol"):
    items: list[NavListItem] = element(tag="li", default=[])


NavInline.model_rebuild()
NavLink.model_rebuild()
NavHeading.model_rebuild()
NavListItem.model_rebuild()
NavList.model_rebuild()


class NavElement(CommonAttributes, tag="nav", search_mode="unordered"):
    h1: NavHeading | None = element(tag="h1", default=None)
    h2: NavHeading | None = element(tag="h2", default=None)
    h3: NavHeading | None = element(tag="h3",
                                    default=None)
    # 1 C:\Users\Ivan\.ewa\epub\nav\4b56dab32ef8d4e8a562e778b49da36f_toc.xhtml
    h4: NavHeading | None = element(tag="h4", default=None)  # 0
    h5: NavHeading | None = element(tag="h5", default=None)  # 0
    h6: NavHeading | None = element(tag="h6", default=None)  # 0

    ol: NavList | None = element(tag="ol", default=None)


class BlockElement(CommonAttributes):
    h1s: list[NavHeading] = element(tag="h1", default=[])  # 50+
    h2s: list[NavHeading] = element(tag="h2", default=[])  # 0
    h3s: list[NavHeading] = element(tag="h3",
                                    default=[])
    # 1 C:\Users\Ivan\.ewa\epub\nav\4b56dab32ef8d4e8a562e778b49da36f_toc.xhtml
    h4s: list[NavHeading] = element(tag="h4", default=[])  # 0
    h5s: list[NavHeading] = element(tag="h5", default=[])  # 0
    h6s: list[NavHeading] = element(tag="h6", default=[])  # 0
    ps: list[NavInline] = element(tag="p", default=[])  # 4
    divs: list[Div] = element(tag="div", default=[])  # 10+
    navs: list[NavElement] = element(tag="nav", default=[])
    sections: list[Section] = element(tag="section",
                                      default=[])
    # 4 C:\Users\Ivan\.ewa\epub\nav\6bfb89338d0e7deef8bfddc973dc531c_toc.xhtml +
    article: Article | None = element(tag="article",
                                      default=None)
    # 1 C:\Users\Ivan\.ewa\epub\nav\6bfb89338d0e7deef8bfddc973dc531c_toc.xhtml
    header: Header | None = element(tag="header",
                                    default=None)
    # 1 C:\Users\Ivan\.ewa\epub\nav\6bfb89338d0e7deef8bfddc973dc531c_toc.xhtml
    footer: Footer | None = element(tag="footer",
                                    default=None)
    # 1 C:\Users\Ivan\.ewa\epub\nav\6bfb89338d0e7deef8bfddc973dc531c_toc.xhtml

    @property
    def nav(self) -> NavElement | None:
        return self.navs[0] if self.navs else None


class Div(BlockElement, tag="div", search_mode="unordered"): ...
class Section(BlockElement, tag="section", search_mode="unordered"): ...
class Article(BlockElement, tag="article", search_mode="unordered"): ...
class Header(BlockElement, tag="header", search_mode="unordered"): ...
class Footer(BlockElement, tag="footer", search_mode="unordered"): ...
class Body(BlockElement, tag="body", search_mode="unordered"): ...


BlockElement.model_rebuild()
Div.model_rebuild()
Section.model_rebuild()
Article.model_rebuild()
Header.model_rebuild()
Footer.model_rebuild()


class HeadLink(CommonAttributes, tag="link"):
    href: str = attr()
    rel: str = attr()
    type: str | None = attr(default=None)


class HeadMeta(BaseXmlModel, tag="meta", nsmap=NAV_NSMAP):
    charset: str | None = attr(default=None)
    content: str | None = attr(default=None)
    http_equiv: str | None = attr(name="http-equiv", default=None)
    name: str | None = attr(default=None)


class HeadStyle(BaseXmlModel, tag="style", nsmap=NAV_NSMAP):
    type: str | None = attr(default=None)
    text: str | None = None


class Head(CommonAttributes, tag="head", search_mode="unordered"):
    title: str | None = element(tag="title", default=None)
    metas: list[HeadMeta] = element(tag="meta", default=[])
    links: list[HeadLink] = element(tag="link", default=[])
    styles: list[HeadStyle] = element(tag="style", default=[])


class NavDocument(CommonAttributes, XMLDocumentModel, tag="html", nsmap=NAV_NSMAP):
    prefix: str | None = attr(default=None)

    head: Head = element()
    body: Body = element()

    __unordered_tags__ = {
        'html', 'head', 'body', 'div', 'section', 'article', 'header', 'footer', 'aside', 'nav', 'li'
    }
    __ignore_xmlns__ = True
