"""Tests for library.epub.recipe_html: translate_text and replace_links.

All test data is generated inline (no repo fixtures): Resource objects are built
the same way as in test_image_recipe, over plain HTML/XHTML bytes.
"""

from io import BytesIO
from zipfile import ZipInfo

from lxml import html as lxml_html

from library.epub.recipe_html import replace_links, translate_text
from library.epub.resources import Resource


def html_resource(markup: str, filename: str = "OEBPS/text/chapter.xhtml") -> Resource:
    data = markup.encode("utf-8")
    info = ZipInfo(filename)
    info.file_size = len(data)
    return Resource(info=info, stream_bytes=lambda i: BytesIO(data))


CHAPTER = """<html>
  <head><title>Chapter</title></head>
  <body>
    <p>Hello world</p>
    <a href="old_target.xhtml">link</a>
    <img src="images/old_picture.png"/>
  </body>
</html>"""


# ---------------------------------------------------------------------------
# translate_text
# ---------------------------------------------------------------------------


def test_translate_text_replaces_mapped_characters():
    resource = html_resource("<p>Hello world</p>")
    table = str.maketrans({"o": "0", "l": "1"})

    translate_text(resource, table)

    assert b"He110 w0r1d" in resource.content


def test_translate_text_leaves_unmapped_text_alone():
    resource = html_resource("<p>Abc Xyz</p>")
    table = str.maketrans({"q": "Q"})  # 'q' does not occur

    original = resource.content
    translate_text(resource, table)

    assert resource.content == original


def test_translate_text_transliterates_unicode():
    resource = html_resource("<p>мир и дом</p>")
    table = str.maketrans({"и": "i"})

    translate_text(resource, table)

    assert "мiр i дом" in resource.content.decode("utf-8")  # cyrillic м/р/д/о/м untouched


def test_translate_text_replaces_everywhere_in_markup():
    """Contract note: the recipe is a raw text substitution - it does not parse
    HTML, so tags and attributes are translated too when they contain mapped
    characters."""
    resource = html_resource('<a href="color.html">red</a>')
    table = str.maketrans({"o": "0"})

    translate_text(resource, table)

    assert b'href="c0l0r.html"' in resource.content
    assert b">red<" in resource.content


def test_translate_text_replaces_invalid_utf8():
    data = b"<p>caf\xe9</p>"  # latin-1 é, invalid utf-8
    info = ZipInfo("page.xhtml")
    info.file_size = len(data)
    resource = Resource(info=info, stream_bytes=lambda i: BytesIO(data))

    translate_text(resource, str.maketrans({"a": "A"}))

    assert "\ufffd".encode("utf-8") in resource.content  # replacement char present
    assert resource.content.startswith(b"<p>cAf")  # a was mapped, \xe9 became U+FFFD


# ---------------------------------------------------------------------------
# replace_links
# ---------------------------------------------------------------------------


def test_replace_links_updates_href_and_src():
    resource = html_resource(CHAPTER)
    table = {
        "old_target.xhtml": "new_target.xhtml",
        "images/old_picture.png": "images/new_picture.webp",
    }

    replace_links(resource, table)

    content = resource.content
    assert b'href="new_target.xhtml"' in content
    assert b'src="images/new_picture.webp"' in content
    assert b"old_target.xhtml" not in content
    assert b"old_picture.png" not in content


def test_replace_links_touches_only_mapped_links():
    resource = html_resource(CHAPTER)
    table = {"old_target.xhtml": "renamed.xhtml"}

    replace_links(resource, table)

    content = resource.content
    assert b'href="renamed.xhtml"' in content
    assert b'images/old_picture.png' in content  # unmapped: untouched


def test_replace_links_leaves_anchors_and_fragments():
    markup = """<html><body>
      <a href="#section">jump</a>
      <a href="chapter2.xhtml#section">go</a>
      <a href="https://example.com/page">ext</a>
    </body></html>"""
    resource = html_resource(markup)
    table = {"chapter2.xhtml#section": "moved.xhtml"}

    replace_links(resource, table)

    content = resource.content
    assert b'href="moved.xhtml"' in content
    assert b'href="#section"' in content  # fragment-only untouched
    assert b"https://example.com/page" in content  # unmapped external untouched


def test_replace_links_handles_multiple_occurrences():
    markup = """<html><body>
      <a href="a.xhtml">1</a><a href="a.xhtml">2</a>
      <img src="a.xhtml"/>
    </body></html>"""
    resource = html_resource(markup)

    replace_links(resource, {"a.xhtml": "b.xhtml"})

    content = resource.content
    assert content.count(b"b.xhtml") == 3
    assert b"a.xhtml" not in content


def test_replace_links_empty_table_reformats_only():
    """Not a byte-level noop: the recipe always re-serializes via pretty_print.
    Semantically, though, nothing changes."""
    resource = html_resource(CHAPTER)

    replace_links(resource, {})

    parsed = lxml_html.document_fromstring(resource.content)
    links = [link for _, _, link, _ in parsed.iterlinks()]
    assert links == ["old_target.xhtml", "images/old_picture.png"]
    assert "Hello world" in resource.content.decode("utf-8")


def test_replace_links_result_still_parses():
    """Whatever pretty-print does, the output must remain a valid document
    with the same links (up to mapping)."""
    resource = html_resource(CHAPTER)
    table = {"old_target.xhtml": "new_target.xhtml"}

    replace_links(resource, table)

    parsed = lxml_html.document_fromstring(resource.content)
    hrefs = [link for element, _, link, _ in parsed.iterlinks() if element.tag == "a"]
    srcs = [link for element, _, link, _ in parsed.iterlinks() if element.tag == "img"]
    assert hrefs == ["new_target.xhtml"]
    assert srcs == ["images/old_picture.png"]
