from xml.etree import ElementTree

import pytest
from lxml import etree
from pydantic_xml import BaseXmlModel

from library.xml.document_pydantic import XMLDocumentModel


class Root(XMLDocumentModel, tag="root"):
    pass


def test_document_serializes_with_lxml():
    document = Root.from_xml_bytes(b"<root/>")
    assert isinstance(document.to_xml_tree(), etree._Element)
    assert etree.fromstring(document.to_xml_bytes()).tag == "root"


def test_standard_library_backend_is_rejected(monkeypatch):
    monkeypatch.setattr(BaseXmlModel, "to_xml_tree", lambda self, **kwargs: ElementTree.Element("root"))
    with pytest.raises(TypeError, match="requires the lxml backend"):
        Root().to_xml_tree()
