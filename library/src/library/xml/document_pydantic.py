from typing import TypeVar

from lxml import etree
from pydantic_xml import BaseXmlModel
from library.xml.document import XMLDocument

ModelT = TypeVar("ModelT", bound=BaseXmlModel)


class XMLDocumentModel(BaseXmlModel, XMLDocument):
    def to_xml_tree(self, skip_empty=True, exclude_none=True, exclude_unset=True) -> etree._Element:
        root = super().to_xml_tree(skip_empty=skip_empty, exclude_none=exclude_none, exclude_unset=exclude_unset)
        if not isinstance(root, etree._Element):
            raise TypeError("XMLDocumentModel requires the lxml backend; disable FORCE_STD_XML")
        return root
