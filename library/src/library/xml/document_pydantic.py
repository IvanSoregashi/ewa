from typing import TypeVar

from lxml.etree import Element
from pydantic_xml import BaseXmlModel
from library.xml.document import XMLDocument

ModelT = TypeVar("ModelT", bound=BaseXmlModel)


class XMLDocumentModel(BaseXmlModel, XMLDocument):
    def to_xml_tree(self, skip_empty=True, exclude_none=True, exclude_unset=True) -> Element:
        return super().to_xml_tree(skip_empty=skip_empty, exclude_none=exclude_none, exclude_unset=exclude_unset)
