import logging
from zipfile import ZipFile

from library.epub.epub import EPUB
from epub.recipe_links import log_links


def book(tmp_path, files):
    path = tmp_path / "links.epub"
    with ZipFile(path, "w") as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return EPUB(path)


def test_link_check_covers_markup_css_and_container(tmp_path, caplog):
    files = {
        "META-INF/container.xml": '<container><rootfile full-path="OEBPS/book.opf"/></container>',
        "OEBPS/book.opf": '<package><item href="chapter.xhtml"/></package>',
        "OEBPS/chapter.xhtml": '<html><head><style>x{background:url(pic%201.png)}</style></head><body><img src="pic%201.png"/><a href="#start"/><a href="https://example.com"/><p style="background:url(pic%201.png)"/></body></html>',
        "OEBPS/nav.xhtml": '<html><a href="chapter.xhtml#start"/></html>',
        "OEBPS/toc.ncx": '<ncx><content src="chapter.xhtml#start"/></ncx>',
        "OEBPS/style.css": 'x{background:url("pic%201.png")}',
        "OEBPS/pic 1.png": b"image",
    }
    epub = book(tmp_path, files)
    with caplog.at_level(logging.DEBUG):
        result = log_links(epub)
    assert result["local"] == 9
    assert result["external"] == 1
    assert result["documents"] == 6
    assert "all inspected local URLs resolved" in caplog.text
    for resource in epub.resources:
        original = files[resource.filename]
        assert resource.content == (original.encode() if isinstance(original, str) else original)


def test_link_check_reports_errors_and_continues(tmp_path, caplog):
    epub = book(
        tmp_path,
        {
            "bad.xml": "<broken",
            "chapter.xhtml": '<html><img src="missing.png"/><a href="bad%2fpath"/></html>',
            "other.xhtml": '<html><a href="#self"/></html>',
        },
    )
    with caplog.at_level(logging.INFO):
        result = log_links(epub)
    assert result["errors"] == result["missing"] == result["invalid"] == result["local"] == 1
    assert "all inspected local URLs resolved" not in caplog.text


def test_base_overrides_and_recovery_are_not_clean_success(tmp_path, caplog):
    epub = book(
        tmp_path,
        {
            "base.xhtml": '<html><base href="https://example.com/"/><img src="x.png"/></html>',
            "recover.html": '<html><body><br><a href="#self">self</a></body></html>',
        },
    )
    with caplog.at_level(logging.INFO):
        result = log_links(epub)
    assert result["unsupported"] == result["recovered"] == 1
    assert result["local"] == 1
    assert "all inspected local URLs resolved" not in caplog.text
