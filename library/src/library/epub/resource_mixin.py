from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol

from lxml import etree, html
from lxml.etree import Element
from lxml.html import HtmlElement

from library.epub.epub_link import EPUBLink
from library.xml.utils import etree_from_bytes

from library.xml.document_pydantic import XMLDocumentModel
import logging
logger = logging.getLogger(__name__)



class HasContent(Protocol):
    _content = None

    @property
    def content(self) -> bytes: ...

    def invalidate_byte_cache(self) -> None: ...


@dataclass(kw_only=True)
class XmlMixin(HasContent):
    _xml: Element = None

    @property
    def xml(self) -> Element:
        if self._xml is None:
            self._xml = etree_from_bytes(self.content)
        return self._xml

    def invalidate_parsed_objects(self) -> None:
        logger.debug(f"{self} invalidating the xml parsed data")
        if self._xml is not None:
            self._xml = None
        super().invalidate_parsed_objects()

    def serialize(self) -> bytes | None:
        if self._xml is not None:
            return etree.tostring(self._xml, pretty_print=True, xml_declaration=True, encoding="utf-8")
        return super().serialize()


@dataclass(kw_only=True)
class XmlDocumentMixin[D: XMLDocumentModel]:
    _document: D | None = None
    document_model: type[D] = None  # must be overwritten by subclass

    @property
    def document(self) -> D:
        if self._document is None:
            self._document: D = self.document_model.from_xml_bytes(self.content)
        return self._document

    def invalidate_parsed_objects(self) -> None:
        logger.debug(f"{self} invalidating the html parsed data")
        if self._document is not None:
            self._document = None
        super().invalidate_parsed_objects()

    def serialize(self) -> bytes | None:
        if self._document is not None:
            return html.tostring(self._document, pretty_print=True)
        return super().serialize()


@dataclass(kw_only=True)
class HtmlMixin(HasContent):
    _html: HtmlElement = None
    linked_to: list[EPUBLink] = field(default_factory=list)

    @property
    def html(self) -> HtmlElement:
        if self._html is None:
            cached_html: HtmlElement = html.document_fromstring(self.content)
            self._html = cached_html

        return self._html

    def invalidate_parsed_objects(self) -> None:
        logger.debug(f"{self} invalidating the html parsed data")
        if self._html is not None:
            self._html = None
        super().invalidate_parsed_objects()

    def serialize(self) -> bytes | None:
        if self._html is not None:
            return html.tostring(self._html, pretty_print=True)
        return super().serialize()

    def parse_links(self) -> list[EPUBLink]:
        logger.debug(f"{self} parsing links")
        return [EPUBLink.from_iterlinks(self.filename, link_data) for link_data in self.html.iterlinks()]
