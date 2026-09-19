from zipfile import ZipFile

import pytest

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.processing import ProcessingContext
from epub.recipe_css import CleanupPandaCSS
from epub.recipe_htmls import RemoveResourceAndManifest, TextTranslator
from epub.verification import MimetypeVerification, OPFPath, SerenePanda, ValidXMLChapters
from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import EpubRole, FileName, MediaType
from library.epub.resources import Resource


@pytest.fixture
def book_path(tmp_path):
    path = tmp_path / "book.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Book</dc:title></metadata>'
            '<manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="font" href="fonts/SerenePanda.ttf" media-type="font/ttf"/>'
            '<item id="style" href="style.css" media-type="text/css"/>'
            '<item id="page" href="page_styles.css" media-type="text/css"/></manifest>'
            '<spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr("chapter.xhtml", '<html><body><p>Encoded</p><img src="cover.png"/></body></html>')
        archive.writestr(FileName.SP_FONT, b"font")
        archive.writestr("style.css", 'body { font-family: "SerenePanda", serif; }')
        archive.writestr(
            "page_styles.css", '@font-face { font-family: "SerenePanda"; src: url(fonts/SerenePanda.ttf); }'
        )
        archive.writestr("notes.txt", "Encoded")
    return path


def test_ordered_context_pipeline_exports_translated_book_without_font(book_path, tmp_path):
    translator = TextTranslator(str.maketrans({"E": "D"}))
    operations = (
        translator,
        RemoveResourceAndManifest(role=EpubRole.FONT, path="serenepanda", flush=False),
        CleanupPandaCSS(),
    )
    destination = tmp_path / "processed.epub"
    with ProcessingContext() as context:
        context.open_epub(book_path)
        for check in (MimetypeVerification(), OPFPath(), SerenePanda(strict=True)):
            context.verify(check)
        for operation in operations:
            chained = context.perform(operation)
        context.verify(ValidXMLChapters())
        context.epub.package_into(destination)
        context.succeed(EPUB(destination).info())

    assert context.result is not None
    assert context.result.success, context.result.details
    assert chained is context
    output = EPUB(destination)
    assert b"Dncoded" in require(output.resources.by_path("chapter.xhtml")).content
    assert require(output.resources.by_path("notes.txt")).content == b"Encoded"
    assert require(output.resources.by_path("style.css")).content == b"body { font-family: serif; }"
    assert require(output.resources.by_path("page_styles.css")).content == b""
    assert output.resources.by_path(FileName.SP_FONT) is None
    assert output.package.manifest_item_by_path(FileName.SP_FONT) is None
    assert context.result.analytics == []
    assert context.replacements == {}
    assert EPUB(book_path).resources.by_path(FileName.SP_FONT) is not None


@pytest.mark.parametrize(
    "selection",
    [
        {"role": EpubRole.FONT},
        {"media_type": MediaType.FONT_TTF},
        {"exact_path": FileName.SP_FONT},
        {"role": EpubRole.FONT, "media_type": MediaType.FONT_TTF, "path": "serenepanda"},
    ],
)
def test_removal_filters_update_inventory_and_manifest(book_path, selection):
    with ProcessingContext() as context:
        context.open_epub(book_path)
        direct_result = RemoveResourceAndManifest(**selection).perform(context)
    # This tests the operation alone; no export/success is requested.
    assert direct_result is None
    assert context.epub.resources.by_path(FileName.SP_FONT) is None
    assert context.epub.package.manifest_item_by_path(FileName.SP_FONT) is None
    assert b"SerenePanda.ttf" not in context.epub.package.resource.content  # Default flush.
    assert context.epub.resources.by_path("chapter.xhtml") is not None
    assert context.analytics == []


def test_no_matching_resources_and_empty_translation_do_nothing(book_path):
    with ProcessingContext() as context:
        context.open_epub(book_path)
        before = {resource.filename: resource.content for resource in context.epub.resources}
        context.perform(TextTranslator({})).perform(
            RemoveResourceAndManifest(role=EpubRole.FONT, exact_path="missing.ttf", flush=False)
        )
        after = {resource.filename: resource.content for resource in context.epub.resources}
    assert after == before
    assert context.analytics == []


def test_removal_still_rejects_spine_dependencies(book_path):
    with ProcessingContext() as context:
        context.open_epub(book_path).perform(RemoveResourceAndManifest(exact_path="chapter.xhtml"))
        pytest.fail("Removal should reject a referenced chapter")
    assert context.result.error == EpubErrorReason.UNKNOWN
    assert "OPF references" in context.result.details
    assert context.epub.resources.by_path("chapter.xhtml") is not None
    assert context.epub.package.manifest_item_by_path("chapter.xhtml") is not None


def test_failed_check_stops_before_operations(book_path):
    with ProcessingContext() as context:
        context.open_epub(book_path)
        context.verify(OPFPath("OEBPS/content.opf")).perform(TextTranslator(str.maketrans({"E": "D"})))
        pytest.fail("The operation must not run after a failed check")
    assert context.result.skip == EpubSkipReason.NON_DEFAULT_OPF
    assert b"Encoded" in context.epub.resources.by_path("chapter.xhtml").content
    assert context.analytics == []


def test_operation_exception_stops_later_operations_without_rollback(book_path):
    class FailingOperation:
        def perform(self, context):
            context.epub.resources.by_path("notes.txt").content = b"Partial edit"
            raise ValueError("Operation failed")

    with ProcessingContext() as context:
        context.open_epub(book_path).perform(FailingOperation()).perform(TextTranslator(str.maketrans({"E": "D"})))
        pytest.fail("Later operation ran")
    assert context.result.error == EpubErrorReason.UNKNOWN
    assert "Operation failed" in context.result.details
    assert context.epub.resources.by_path("notes.txt").content == b"Partial edit"
    assert b"Encoded" in context.epub.resources.by_path("chapter.xhtml").content


def test_css_operation_selects_its_cleanup_and_can_be_reused(book_path):
    cleanup = CleanupPandaCSS()
    with ProcessingContext() as first, ProcessingContext() as second:
        first.open_epub(book_path)
        second.open_epub(book_path)
        first.epub.resources.add(Resource.from_bytes("plain.css", b"body { color: black; }"))
        cleanup.perform(first)
        cleanup.perform(second)
    assert require(first.epub.resources.by_path("plain.css")).content == b"body { color: black; }"
    for context in (first, second):
        assert b"SerenePanda" not in require(context.epub.resources.by_path("style.css")).content
        assert require(context.epub.resources.by_path("page_styles.css")).content == b""
        assert require(context.epub.resources.by_path("notes.txt")).content == b"Encoded"
        assert context.analytics == []
