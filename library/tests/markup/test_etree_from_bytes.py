"""Tests for library.xml.utils.etree_from_bytes: strict XML parse with
self-healing retries for known defect classes."""

import pytest
from lxml import etree

from library.xml.utils import etree_from_bytes, fix_invalid_ampersands, fix_named_entities


def test_parses_valid_xml():
    root = etree_from_bytes(b"<root><a>text</a></root>")
    assert root.tag == "root"
    element = root.find("a")
    assert element is not None
    assert element.text == "text"


def test_default_profile_strips_comments_and_blank_text():
    root = etree_from_bytes(b"<root>\n  <!-- note -->\n  <a>x</a>\n</root>")
    assert root.find("a") is not None
    assert not any(child.tag is etree.Comment for child in root)


def test_custom_parser_profile_is_honored():
    parser = etree.XMLParser(huge_tree=True)  # keeps comments and blank text
    root = etree_from_bytes(b"<root>\n  <!-- note -->\n  <a>x</a>\n</root>", parser)
    assert any(child.tag is etree.Comment for child in root)


def test_heals_raw_ampersands():
    root = etree_from_bytes(b"<root><p>AT&T and sons</p></root>")
    element = root.find("p")
    assert element is not None
    assert element.text == "AT&T and sons"


def test_heals_named_entities():
    root = etree_from_bytes(b"<root><p>caf&eacute;&nbsp;au lait</p></root>")
    element = root.find("p")
    assert element is not None
    assert element.text == "caf\xe9\xa0au lait"


def test_valid_xml_entities_untouched():
    root = etree_from_bytes(b"<root><p>a &amp; b &lt; c &quot;d&quot; &apos;e&apos;</p></root>")
    element = root.find("p")
    assert element is not None
    assert element.text == "a & b < c \"d\" 'e'"


def test_combination_heals_across_retries():
    root = etree_from_bytes(b"<root><p>a &amp; b</p><p>AT&T</p><p>x&nbsp;y</p></root>")
    assert [p.text for p in root.findall("p")] == ["a & b", "AT&T", "x\xa0y"]


def test_unknown_entity_still_raises():
    with pytest.raises(etree.XMLSyntaxError):
        etree_from_bytes(b"<root><p>&foobar;</p></root>")


def test_heals_missing_opf_namespace():
    root = etree_from_bytes(b'<package version="2.0"><opf:meta>data</opf:meta></package>')
    assert root.nsmap.get("opf") == "http://www.idpf.org/2007/opf"
    assert root.find("opf:meta", namespaces={"opf": "http://www.idpf.org/2007/opf"}) is not None


def test_fix_invalid_ampersands_leaves_entity_like_sequences():
    assert fix_invalid_ampersands("a & b&nbsp;c") == "a &amp; b&nbsp;c"
    assert fix_invalid_ampersands("AT&T") == "AT&amp;T"


def test_fix_named_entities_leaves_xml_safe_and_unknown_ones():
    assert fix_named_entities("a &amp; b") == "a &amp; b"
    assert fix_named_entities("&nbsp;") == "\xa0"
    assert fix_named_entities("&foobar;") == "&foobar;"
