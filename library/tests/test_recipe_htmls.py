"""Tests for epub.recipe_htmls: book-level link replacement and the unmatched
report. Synthetic resources, no fixtures."""

from library.epub.recipe_htmls import replace_links_in_htmls
from library.epub.resources import ResourceIndex


def chapter(markup: str, filename: str) -> tuple[str, bytes]:
    return filename, markup.encode("utf-8")


def build_index(*chapters: tuple[str, bytes]) -> ResourceIndex:
    from io import BytesIO
    from zipfile import ZipInfo

    from library.epub.resources import Resource

    entries = []
    for filename, data in chapters:
        info = ZipInfo(filename)
        info.file_size = len(data)
        entries.append(Resource(info=info, stream_bytes=lambda i, d=data: BytesIO(d)))
    return ResourceIndex.from_resource_list(entries)


def reference_chapter(filename: str, form: str) -> tuple[str, bytes]:
    markup = {
        "img": '<html xmlns="http://www.w3.org/1999/xhtml"><body><img src="replaced.png"/></body></html>',
        "xlink": (
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<body><svg><image xlink:href="replaced.png"/></svg></body></html>'
        ),
        "non-link": (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><div data-ref="replaced.png"/></body></html>'
        ),
        "empty": '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>nothing</p></body></html>',
    }[form]
    return chapter(markup, filename)


def test_replaces_across_all_documents():
    index = build_index(
        reference_chapter("OEBPS/text/ch1.xhtml", "img"),
        reference_chapter("OEBPS/text/ch2.xhtml", "xlink"),
    )

    unmatched = replace_links_in_htmls(index, {"OEBPS/text/replaced.png": "OEBPS/text/replaced.jpg"})

    assert unmatched == {}
    for resource in index:
        content = resource.content
        assert b"replaced.jpg" in content
        assert b"replaced.png" not in content


def test_unmatched_reports_orphan_entries():
    """An entry no document references stays in the unmatched report."""
    index = build_index(
        reference_chapter("OEBPS/text/ch1.xhtml", "img"),
        reference_chapter("OEBPS/text/ch2.xhtml", "empty"),
    )

    unmatched = replace_links_in_htmls(index, {
        "OEBPS/text/replaced.png": "OEBPS/text/replaced.jpg",
        "OEBPS/text/orphan.png": "OEBPS/text/orphan.jpg",
    })

    assert unmatched == {"OEBPS/text/orphan.png": "OEBPS/text/orphan.jpg"}


def test_unmatched_keeps_found_but_not_replaced_entries():
    """A reference in a form the discovery does not cover (data-ref) was found
    but not replaced: it must stay in the report, not disappear."""
    index = build_index(
        reference_chapter("OEBPS/text/ch1.xhtml", "non-link"),
    )

    unmatched = replace_links_in_htmls(index, {"OEBPS/text/replaced.png": "OEBPS/text/replaced.jpg"})

    assert unmatched == {"OEBPS/text/replaced.png": "OEBPS/text/replaced.jpg"}
    assert b"replaced.png" in index[0].content  # untouched
