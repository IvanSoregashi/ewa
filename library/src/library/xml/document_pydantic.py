from typing import TypeVar
from pydantic_xml import BaseXmlModel
from library.xml.document import XMLDocument

ModelT = TypeVar("ModelT", bound=BaseXmlModel)


class XMLDocumentModel(BaseXmlModel, XMLDocument): ...
