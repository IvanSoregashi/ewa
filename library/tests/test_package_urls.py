import pytest

from library.epub.epub import EPUB
from library.epub.package_urls import archive_path, local_target, rebase_href
from library.epub.resources import Resource
from .test_package import make_epub, relocation_state


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "..",
        "/book.opf",
        "../book.opf",
        "a/../../book.opf",
        "C:/book.opf",
        "a\\book.opf",
        "book.opf?x",
        "book.opf#x",
        "a/",
        "a/..",
        "a/.",
        "a\x00.opf",
    ],
)
def test_invalid_relocation_is_rejected_without_changes(tmp_path, path):
    epub = make_epub(tmp_path)
    before = relocation_state(epub)
    with pytest.raises(ValueError):
        epub.package.relocate(path)
    assert relocation_state(epub) == before


def test_normalized_destination_is_used_for_collision_detection(tmp_path):
    epub = make_epub(tmp_path, extra_opf=True)
    before = relocation_state(epub)
    with pytest.raises(ValueError, match="already exists"):
        epub.package.relocate("folder/../unused.opf")
    assert relocation_state(epub) == before
    assert not epub.package.relocate("OEBPS/./content.opf")


@pytest.mark.parametrize("path", ["OEBPS/text", "OEBPS/text/chapter.xhtml/book.opf"])
def test_file_directory_conflicts_are_rejected(tmp_path, path):
    epub = make_epub(tmp_path)
    before = relocation_state(epub)
    with pytest.raises(ValueError, match="conflicts"):
        epub.package.relocate(path)
    assert relocation_state(epub) == before


@pytest.mark.parametrize(
    "href, expected",
    [
        ("text/a%20b.xhtml?view=1#part", "../OEBPS/text/a%20b.xhtml?view=1#part"),
        ("text/100%25.xhtml?#", "../OEBPS/text/100%25.xhtml?#"),
        ("#metadata", "#metadata"),
        ("?mode=1#metadata", "?mode=1#metadata"),
        ("https://example.com/a%20b?q=x#p", "https://example.com/a%20b?q=x#p"),
        ("//example.com/a", "//example.com/a"),
    ],
)
def test_rebase_url_components(href, expected):
    assert rebase_href("OEBPS/content.opf", "new/book.opf", href) == expected


@pytest.mark.parametrize(
    "href",
    [
        "../../escape.xhtml",
        "%2e%2e/%2e%2e/escape.xhtml",
        "text/a%2fb.xhtml",
        "text/a%5cb.xhtml",
        "text/bad%.xhtml",
        "text/%FF.xhtml",
        "/absolute.xhtml",
    ],
)
def test_invalid_local_hrefs_leave_relocation_unchanged(tmp_path, href):
    epub = make_epub(tmp_path)
    epub.package.document.manifest.items[0].href = href
    before = relocation_state(epub)
    with pytest.raises(ValueError):
        epub.package.relocate("new.opf")
    assert relocation_state(epub) == before


def test_encoded_paths_survive_relocation_export_and_reopen(tmp_path):
    epub = make_epub(tmp_path)
    resource = Resource.from_bytes("OEBPS/text/глава 100%.xhtml", b"chapter")
    epub.resources.add(resource)
    entry = epub.package.document.manifest.items[0]
    entry.href = "text/%D0%B3%D0%BB%D0%B0%D0%B2%D0%B0%20100%25.xhtml?view=1#part"
    assert epub.package.resource_for_href(entry.href) is resource
    assert epub.package.relocate("draft/../Новая папка/book 100%.opf")
    assert epub.package.resource.filename == "Новая папка/book 100%.opf"
    assert epub.package.resource_for_href(entry.href) is resource
    output = tmp_path / "out.epub"
    epub.package_into(output)
    reopened = EPUB(output).package
    assert reopened.resource.filename == epub.package.resource.filename
    resource = reopened.resource_for_href(reopened.document.manifest.items[0].href)
    assert resource is not None
    assert resource.content == b"chapter"
    assert reopened.relocate("content.opf")


def test_literal_percent_path_is_not_decoded_twice():
    assert archive_path("folder/../100%20.opf") == "100%20.opf"
    assert local_target("book.opf", "100%2520.xhtml") == ("100%20.xhtml", "")
