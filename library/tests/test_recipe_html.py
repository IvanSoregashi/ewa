"""Tests for library.epub.recipe_html: translate_text and replace_links.

All test data is generated inline (no repo fixtures): Resource objects are built
the same way as in test_image_recipe, over plain HTML/XHTML bytes.
"""

from io import BytesIO
from zipfile import ZipInfo

from lxml import etree, html as lxml_html

from library.epub.recipe_html import replace_gifs_with_videos, replace_links, translate_text
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
    # table keys/values are ARCHIVE paths; the document at OEBPS/text/chapter.xhtml
    # refers to them via document-relative links
    table = {
        "OEBPS/text/old_target.xhtml": "OEBPS/text/new_target.xhtml",
        "OEBPS/text/images/old_picture.png": "OEBPS/text/images/new_picture.webp",
    }

    replace_links(resource, table)

    content = resource.content
    assert b'href="new_target.xhtml"' in content
    assert b'src="images/new_picture.webp"' in content
    assert b"old_target.xhtml" not in content
    assert b"old_picture.png" not in content


def test_replace_links_touches_only_mapped_links():
    resource = html_resource(CHAPTER)
    table = {"OEBPS/text/old_target.xhtml": "OEBPS/text/renamed.xhtml"}

    replace_links(resource, table)

    content = resource.content
    assert b'href="renamed.xhtml"' in content
    assert b"images/old_picture.png" in content  # unmapped: untouched


def test_replace_links_leaves_anchors_and_fragments():
    markup = """<html><body>
      <a href="#section">jump</a>
      <a href="chapter2.xhtml#section">go</a>
      <a href="https://example.com/page">ext</a>
    </body></html>"""
    resource = html_resource(markup)
    table = {"OEBPS/text/chapter2.xhtml#section": "OEBPS/text/moved.xhtml"}

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

    replace_links(resource, {"OEBPS/text/a.xhtml": "OEBPS/text/b.xhtml"})

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
    table = {"OEBPS/text/old_target.xhtml": "OEBPS/text/new_target.xhtml"}

    replace_links(resource, table)

    parsed = lxml_html.document_fromstring(resource.content)
    hrefs = [link for element, _, link, _ in parsed.iterlinks() if element.tag == "a"]
    srcs = [link for element, _, link, _ in parsed.iterlinks() if element.tag == "img"]
    assert hrefs == ["new_target.xhtml"]
    assert srcs == ["images/old_picture.png"]


def test_replace_links_pretty_print_flag_controls_serialization():
    markup = '<html><body><a href="old.xhtml">x</a></body></html>'
    table = {"OEBPS/text/old.xhtml": "OEBPS/text/new.xhtml"}

    pretty_resource = html_resource(markup)
    replace_links(pretty_resource, table, pretty_print_result=True)
    plain_resource = html_resource(markup)
    replace_links(plain_resource, table, pretty_print_result=False)

    assert b"new.xhtml" in pretty_resource.content
    assert b"new.xhtml" in plain_resource.content
    assert b"\n" in pretty_resource.content  # pretty-print added indentation
    plain_body = plain_resource.content.split(b"?>", 1)[-1].lstrip(b"\n")
    assert b"\n" not in plain_body  # plain serialization added no indentation


# ---------------------------------------------------------------------------
# XML-preserving serialization (option A: chapters stay valid parseable XML)
# ---------------------------------------------------------------------------

XHTML_CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter</title></head>
  <body>
    <p>Hello <br/> world</p>
    <a href="old_target.xhtml">link</a>
    <img src="images/old_picture.png" alt="x"/>
  </body>
</html>"""


def test_replace_links_output_stays_valid_xml():
    """Void elements stay self-closed, the XML declaration and namespaces
    survive: the output passes verify_chapter_xml."""
    resource = html_resource(XHTML_CHAPTER)
    table = {"OEBPS/text/old_target.xhtml": "OEBPS/text/new_target.xhtml"}

    replace_links(resource, table)

    content = resource.content
    etree.fromstring(content)  # raises if the output is not well-formed XML
    assert b'href="new_target.xhtml"' in content
    assert b"<br/>" in content  # not <br>
    assert b'xmlns="http://www.w3.org/1999/xhtml"' in content
    assert b"<?xml" in content


def test_replace_links_falls_back_to_html_parse_for_broken_xml():
    """Non-well-formed sources still get their links rewritten, and the output
    is still XML-serialized."""
    resource = html_resource('<html><body><p>x<br><p>y <a href="old.xhtml">go</a></body></html>')

    replace_links(resource, {"OEBPS/text/old.xhtml": "OEBPS/text/new.xhtml"})

    parsed = lxml_html.document_fromstring(resource.content)
    assert [link for _, _, link, _ in parsed.iterlinks()] == ["new.xhtml"]
    etree.fromstring(resource.content)  # output is XML despite the HTML-parse fallback


# ---------------------------------------------------------------------------
# replace_gifs_with_videos (oversized animation -> device-standard video tag)
# ---------------------------------------------------------------------------


def make_video_table(**overrides) -> dict[str, VideoTagInfo]:
    from library.epub.recipe_html import VideoTagInfo

    return {
        "OEBPS/text/images/old.gif": VideoTagInfo(
            video_path="OEBPS/text/images/old.mp4",
            poster_path="OEBPS/text/images/old.jpg",
            width=768,
            height=1152,
            alt="old.gif",
            **overrides,
        )
    }


GIF_CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter</title></head>
  <body>
    <p>before</p>
    <img src="images/old.gif" alt="animation"/>
    <img src="images/other.png" alt="kept"/>
    <p>after</p>
  </body>
</html>"""


def test_replace_gifs_with_videos_replaces_matching_img():
    resource = html_resource(GIF_CHAPTER)

    replaced = replace_gifs_with_videos(resource, make_video_table())

    assert replaced == 1
    content = resource.content
    assert b'<video src="images/old.mp4" poster="images/old.jpg"' in content
    assert b'controls="controls"' in content
    assert b'preload="metadata"' in content
    assert b'width="768"' in content and b'height="1152"' in content
    assert b'<source src="images/old.mp4" type="video/mp4"/>' in content
    assert b'<img src="images/old.jpg" alt="old.gif"/>' in content
    assert b'src="images/other.png"' in content  # unmapped img untouched
    assert b'src="images/old.gif"' not in content  # gif reference gone (alt label may keep the name)
    etree.fromstring(content)  # output stays valid parseable XML


def test_replace_gifs_with_videos_no_match_leaves_document_valid():
    resource = html_resource(GIF_CHAPTER)

    replaced = replace_gifs_with_videos(resource, {})

    assert replaced == 0
    assert b"<img" in resource.content
    assert b"<video" not in resource.content
    etree.fromstring(resource.content)
