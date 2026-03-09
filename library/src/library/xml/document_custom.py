from typing import TypeVar
from lxml import etree

from library.xml.document import XMLDocument

T = TypeVar("T", bound="XMLDocumentSchema")


class XMLElement:
    """Base class for descriptor-based XML models backed by lxml.

    All descriptor fields from fields.py operate on self._elem.

    Subclasses can declare tags and namespaces via class arguments:
        class MyModel(XMLElement, tag="tagname", ns="http://...", nsmap={...}):
            ...
    """

    __tag__: str = ""
    __ns__: str = ""
    __nsmap__: dict = {}

    def __init_subclass__(
        cls,
        tag: str | None = None,
        ns: str | None = None,
        nsmap: dict | None = None,
        **kwargs,
    ):
        super().__init_subclass__(**kwargs)
        if tag is not None:
            cls.__tag__ = tag
        if ns is not None:
            cls.__ns__ = ns
        if nsmap is not None:
            # lxml expects None for the default namespace prefix, not ""
            # TODO: make this better
            cls.__nsmap__ = {(k if k != "" else None): v for k, v in nsmap.items()}

    def __init__(self, elem: etree.Element | None = None):
        self._elem = elem

    @classmethod
    def create(cls, tag: str | None = None, **kwargs):
        """Create a new XMLElement instance with its own lxml element."""
        final_tag = tag or cls.__tag__
        if not final_tag:
            raise ValueError(f"{cls.__name__} has no __tag__ and none provided.")

        clark = f"{{{cls.__ns__}}}{final_tag}" if cls.__ns__ else final_tag
        elem = etree.Element(clark, nsmap=cls.__nsmap__)
        instance = cls(elem)
        for k, v in kwargs.items():
            setattr(instance, k, v)
        return instance


class XMLDocumentSchema(XMLDocument, XMLElement):
    """
    Base class for descriptor-based XML models backed by lxml.

    All descriptor fields from fields.py operate on self._elem.
    """

    def to_xml(
        self,
        encoding: str = "utf-8",
        xml_declaration: bool = True,
        exclude_none: bool = False,
        pretty_print: bool = True,
    ) -> bytes:
        exclude_none: bool  # for compatibility
        return etree.tostring(
            self._elem,
            encoding=encoding,
            xml_declaration=xml_declaration,
            pretty_print=pretty_print,
        )

    def to_xml_tree(
        self,
        *,
        skip_empty: bool = False,
        exclude_none: bool = False,
        exclude_unset: bool = False,
    ) -> etree.Element:
        return self._elem

    @classmethod
    def from_xml_tree(cls, root: etree.Element, context: dict | None = None) -> XMLDocument:
        return cls(root)
