import logging
from io import BytesIO
from os import PathLike
from pathlib import Path
from typing import Type, TypeVar
from library.xml.utils import etree_from_bytes
from lxml import etree

logger = logging.getLogger(__name__)
T = TypeVar("T")


class XMLDocument:
    def to_xml(self, exclude_none=True, encoding="utf-8", xml_declaration=True, pretty_print=True) -> bytes:
        logger.error("NotImplemented method `to_xml` of XMLDocument was called.")
        raise NotImplementedError()

    def to_xml_tree(
        self,
        *,
        skip_empty: bool = False,
        exclude_none: bool = False,
        exclude_unset: bool = False,
    ) -> etree.Element:
        logger.error("NotImplemented method `to_xml` of XMLDocument was called.")
        raise NotImplementedError()

    def to_xml_bytes(self, encoding: str = "utf-8", pretty_print: bool = True) -> bytes:
        return self.to_xml(exclude_none=True, encoding=encoding, xml_declaration=True, pretty_print=pretty_print)

    def to_xml_file(self, path: str | PathLike) -> None:
        Path(path).write_bytes(self.to_xml_bytes())

    @property
    def bytesio(self):
        return BytesIO(self.to_xml_bytes())

    @classmethod
    def from_xml_tree(cls: Type[T], root: etree.Element) -> T:
        logger.error("NotImplemented method `from_xml_tree` of XMLDocument was called.")
        raise NotImplementedError()

    @classmethod
    def from_xml_bytes(cls: Type[T], xml_bytes: bytes) -> T:
        root = etree_from_bytes(xml_bytes)
        return cls.from_xml_tree(root=root)

    @classmethod
    def from_path(cls: Type[T], path: str | PathLike) -> T:
        xml_bytes = Path(path).read_bytes()
        return cls.from_xml_bytes(xml_bytes)
