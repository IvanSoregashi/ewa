from pydantic_xml import BaseXmlModel, attr, element
from library.xml.document_pydantic import XMLDocumentModel
from library.epub.epub_namespaces import NamespacePrefix, NCX_NSMAP


class Meta(BaseXmlModel, tag="meta", nsmap=NCX_NSMAP):
    name: str = attr()
    content: str = attr()
    scheme: str | None = attr(default=None)


class Head(BaseXmlModel, tag="head", nsmap=NCX_NSMAP):
    metas: list[Meta] = element(tag="meta", default=[])


class TextElement(BaseXmlModel, nsmap=NCX_NSMAP):
    text: str | None = element(tag="text", default=None)


class Content(BaseXmlModel, tag="content", nsmap=NCX_NSMAP):
    src: str = attr()


class NavPoint(BaseXmlModel, tag="navPoint", nsmap=NCX_NSMAP):
    id: str | None = attr(default=None)
    class_attr: str | None = attr(name="class", default=None)
    play_order: int | None = attr(name="playOrder", default=None)

    nav_label: TextElement | None = element(tag="navLabel", default=None)
    content: Content = element()
    nav_points: list[NavPoint] = element(tag="navPoint", default=[])


class NavMap(BaseXmlModel, tag="navMap", nsmap=NCX_NSMAP):
    nav_infos: list[TextElement] = element(tag="navInfo", default=[])
    nav_points: list[NavPoint] = element(tag="navPoint", default=[])


class PageTarget(BaseXmlModel, tag="pageTarget", nsmap=NCX_NSMAP):
    id: str | None = attr(default=None)
    value: str | None = attr(default=None)
    type: str | None = attr(default=None)
    class_attr: str | None = attr(name="class", default=None)
    play_order: int | None = attr(name="playOrder", default=None)

    nav_label: TextElement | None = element(tag="navLabel", default=None)
    content: Content = element()


class PageList(BaseXmlModel, tag="pageList", nsmap=NCX_NSMAP):
    id: str | None = attr(default=None)
    class_attr: str | None = attr(name="class", default=None)
    nav_label: TextElement | None = element(tag="navLabel", default=None)
    nav_infos: list[TextElement] = element(tag="navInfo", default=[])
    page_targets: list[PageTarget] = element(tag="pageTarget", default=[])


class NavTarget(BaseXmlModel, tag="navTarget", nsmap=NCX_NSMAP):
    id: str = attr()
    class_attr: str | None = attr(name="class", default=None)
    value: str | None = attr(default=None)
    play_order: int | None = attr(name="playOrder", default=None)

    nav_label: TextElement | None = element(tag="navLabel", default=None)
    content: Content = element()


class NavList(BaseXmlModel, tag="navList", nsmap=NCX_NSMAP):
    id: str | None = attr(default=None)
    class_attr: str | None = attr(name="class", default=None)
    nav_label: TextElement | None = element(tag="navLabel", default=None)
    nav_infos: list[TextElement] = element(tag="navInfo", default=[])
    nav_targets: list[NavTarget] = element(tag="navTarget", default=[])


class NCXDocument(XMLDocumentModel, tag=NamespacePrefix.NCX, nsmap=NCX_NSMAP, search_mode="unordered"):
    version: str | None = attr(default=None)
    xml_lang: str | None = attr(name="lang", ns=NamespacePrefix.XML, default=None)
    dir: str | None = attr(default=None)

    head: Head = element()
    doc_authors: list[TextElement] = element(tag="docAuthor", default=[])
    doc_title: TextElement | None = element(tag="docTitle", default=None)
    nav_map: NavMap = element(tag="navMap")
    nav_lists: list[NavList] = element(tag="navList", default=[])
    page_list: PageList | None = element(tag="pageList", default=None)

    __unordered_tags__ = {'head', 'ncx'}

