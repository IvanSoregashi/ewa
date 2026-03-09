from pathlib import Path

import pytest
from lxml import etree

from library.xml.document import XMLDocument
from library.xml.document_custom import XMLDocumentSchema
from library.xml.document_pydantic import XMLDocumentModel
from library.xml.utils import get_facts

CONTAINER_PATH = "tests/samples/empty_container.xml"
CONTAINER_XML = b'<?xml version="1.0" encoding="utf-8"?><container></container>'


@pytest.fixture(params=[XMLDocumentModel, XMLDocumentSchema])
def document_class(request: pytest.FixtureRequest) -> XMLDocument:
    d_class: XMLDocument = request.param
    return d_class


def test_make_document_from_bytes(document_class):
    class container(document_class): ...

    doc = container.from_xml_bytes(CONTAINER_XML)
    assert get_facts(doc.to_xml_bytes()) == get_facts(CONTAINER_XML)


def test_make_document_from_etree(document_class):
    class container(document_class): ...

    tree = etree.fromstring(CONTAINER_XML)
    doc = container.from_xml_tree(tree)
    assert get_facts(doc.to_xml_bytes()) == get_facts(CONTAINER_XML)


def test_make_document_from_path(document_class):
    class container(document_class): ...
    path = Path(CONTAINER_PATH)
    doc = container.from_path(path)
    assert get_facts(doc.to_xml_bytes()) == get_facts(path.read_bytes())
