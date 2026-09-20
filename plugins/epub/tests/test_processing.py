import io
import pickle
from contextlib import contextmanager
from zipfile import ZipFile

import pytest
from sqlalchemy import inspect
from sqlmodel import Field, SQLModel

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.processing import ProcessingContext
from epub.processing_run import ProcessingRun
from epub.verification import MimetypeVerification, OPFPath, SerenePanda
from library.asserts import require
from library.epub.epub import EPUB
from library.epub.resources import Resource, ResourceIndex
from library.epub.source import ZipFileSource


class ProcessingTestRecord(SQLModel, table=True):
    """Synthetic analytics; no engine or table creation is needed."""

    __tablename__ = "processing_context_test_records"

    id: int | None = Field(default=None, primary_key=True)
    description: str


@pytest.fixture
def book_path(tmp_path):
    path = tmp_path / "book.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("chapter.xhtml", "<html><body>Original</body></html>")
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>Synthetic book</dc:title></metadata>"
            '<manifest><item id="chapter" href="chapter.xhtml" '
            'media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="chapter"/></spine></package>',
        )
    return path


@pytest.mark.parametrize("message", ["", "Book rejected"])
def test_failure_message_stops_processing_even_when_empty(book_path, message):
    class RejectBook:
        skip_reason = EpubSkipReason.NOT_IMPLEMENTED

        def verify(self, context) -> str | None:
            return message

    with ProcessingContext() as context:
        context.open_epub(book_path).verify(RejectBook())
        pytest.fail("A failure message must stop processing")

    result = require(context.result)
    assert result.skip == EpubSkipReason.NOT_IMPLEMENTED
    assert result.details == message
    assert result.error is None


def test_contexts_have_independent_working_state(book_path):
    with ProcessingContext() as first, ProcessingContext() as second:
        first.open_epub(book_path)
        second.open_epub(book_path)
        first.replacements["cover.png"] = "cover.webp"
        first.analytics.append(ProcessingTestRecord(description="First book edited"))
        require(first.epub.resources.by_path("chapter.xhtml")).content = b"edited"

        assert second.replacements == {}
        assert second.analytics == []
        assert b"Original" in require(second.epub.resources.by_path("chapter.xhtml")).content


def test_managed_success_keeps_source_open_and_returns_detached_result(book_path, tmp_path):
    with ProcessingContext() as context:
        assert context.result is None
        assert context.open_epub(str(book_path)).verify(MimetypeVerification()).verify(OPFPath()) is context
        assert isinstance(context.epub.source, ZipFileSource)
        handle = context.epub.source.zip_file
        assert handle.fp is not None
        with context.epub.keep_open():
            assert context.epub.source.zip_file is handle
        assert handle.fp is not None
        require(context.epub.resources.by_path("chapter.xhtml")).content = b"<html><body>Edited</body></html>"
        destination = tmp_path / "processed.epub"
        context.epub.package_into(destination)
        output = EPUB(destination)
        assert b"Edited" in require(output.resources.by_path("chapter.xhtml")).content
        new_info = output.info()
        context.succeed(new_info)
        assert context.result is None  # Cleanup can still fail.

    assert handle.fp is None
    assert context.epub.source._zip_file is None
    assert context.result is not None
    assert context.result.success
    assert context.result.input_path == str(book_path)
    assert context.result.original_epub is not None
    assert context.result.original_epub.title == "Synthetic book"
    assert context.result.new_epub == new_info
    assert pickle.loads(pickle.dumps(context.result)).model_dump() == context.result.model_dump()


@pytest.mark.parametrize("status", ["success", "skip", "error"])
def test_outcomes_retain_evidence_and_exclude_live_resources(book_path, tmp_path, status):
    record = ProcessingTestRecord(description="Chapter edited")
    failed_check = SerenePanda()
    failed_check.skip_reason = EpubSkipReason.NOT_IMPLEMENTED
    with ProcessingContext() as context:
        context.open_epub(book_path).verify(OPFPath())
        context.analytics.append(record)
        chapter = require(context.epub.resources.by_path("chapter.xhtml"))
        chapter.content = b"<html><body>Edited</body></html>"
        context.replacements["cover.png"] = "cover.webp"
        if status == "success":
            destination = tmp_path / "output.epub"
            context.epub.package_into(destination)
            context.succeed(EPUB(destination).info())
        elif status == "skip":
            context.verify(failed_check)
            pytest.fail("Failed check did not stop the block")
        else:
            raise ValueError("Later operation failed")

    outcome = context.result
    assert outcome is not None
    assert outcome.success == (status == "success")
    assert outcome.skip == (EpubSkipReason.NOT_IMPLEMENTED if status == "skip" else None)
    assert outcome.error == (EpubErrorReason.UNKNOWN if status == "error" else None)
    assert outcome.original_epub == context.original_epub
    if status == "skip":
        assert "font not found" in outcome.details
    if status == "error":
        assert "ValueError" in outcome.details
        assert "Later operation failed" in outcome.details
    assert outcome.analytics == [record]
    assert inspect(record).transient
    assert inspect(record).session is None
    assert record.id is None
    assert b"Edited" in chapter.content
    assert b"Original" in context.epub.source.read_bytes("chapter.xhtml")
    assert context.replacements == {"cover.png": "cover.webp"}

    class OutcomePickler(pickle.Pickler):
        def persistent_id(self, obj):
            assert not isinstance(obj, (ProcessingContext, EPUB, Resource, ResourceIndex, ZipFileSource))
            return None

    with context.epub.keep_open():
        buffer = io.BytesIO()
        OutcomePickler(buffer).dump(outcome)
    restored = pickle.loads(buffer.getvalue())
    assert restored.analytics[0].description == record.description
    assert not hasattr(restored, "replacements")
    context.analytics.clear()
    assert outcome.analytics == [record]


@pytest.mark.parametrize("kind", ["missing", "invalid_archive", "invalid_metadata"])
def test_setup_failure_returns_reportable_outcome_without_outer_catch(tmp_path, kind, capsys):
    path = tmp_path / f"{kind}.epub"
    if kind == "invalid_archive":
        path.write_bytes(b"not an archive")
    elif kind == "invalid_metadata":
        with ZipFile(path, "w") as archive:
            archive.writestr("content.opf", "<broken")

    with ProcessingContext() as context:
        context.open_epub(path)
        pytest.fail("Setup failure did not stop the block")

    outcome = context.result
    assert outcome is not None
    assert outcome.error == EpubErrorReason.UNKNOWN
    assert not outcome.success
    assert outcome.original_epub is None
    assert outcome.input_path == str(path)
    assert outcome.details
    assert pickle.loads(pickle.dumps(outcome)).model_dump() == outcome.model_dump()
    outcome.report()
    outcome.short_report()
    output = capsys.readouterr().out
    assert path.name in output
    assert "unknown size" in output
    if path.exists():
        path.unlink()  # Windows refuses this if the archive handle leaked.


def test_source_open_failure_keeps_input_and_earlier_evidence(book_path, monkeypatch):
    @contextmanager
    def cannot_open(self):
        raise PermissionError("Cannot open source")
        yield

    monkeypatch.setattr(ZipFileSource, "open", cannot_open)
    record = ProcessingTestRecord(description="Input selected")
    with ProcessingContext() as context:
        context.analytics.append(record)
        context.open_epub(book_path)
        pytest.fail("Opening failure did not stop the block")

    assert context.result is not None
    assert context.result.input_path == str(book_path)
    assert context.result.original_epub is None
    assert context.result.error == EpubErrorReason.UNKNOWN
    assert "PermissionError" in context.result.details
    assert context.result.analytics == [record]


def test_metadata_failure_closes_acquired_source_without_retry(book_path, monkeypatch):
    acquired = []

    def fail_info(epub):
        acquired.append(epub.source.zip_file)
        raise OSError("Metadata read failed")

    monkeypatch.setattr(EPUB, "info", fail_info)
    with ProcessingContext() as context:
        context.open_epub(book_path)
        pytest.fail("Metadata failure did not stop the block")

    assert len(acquired) == 1
    assert acquired[0].fp is None
    assert context.result is not None
    assert context.result.original_epub is None
    assert context.result.input_path == str(book_path)
    assert "Metadata read failed" in context.result.details


def test_check_exception_is_error_instead_of_skip(book_path):
    class BrokenCheck:
        skip_reason = EpubSkipReason.NOT_IMPLEMENTED

        def verify(self, context):
            raise ValueError("Cannot inspect chapter")

    with ProcessingContext() as context:
        context.open_epub(book_path).verify(OPFPath()).verify(BrokenCheck())
        pytest.fail("Broken check did not stop the block")

    assert context.result is not None
    assert context.result.error == EpubErrorReason.UNKNOWN
    assert context.result.skip is None
    assert "Cannot inspect chapter" in context.result.details


@pytest.mark.parametrize("open_book", [False, True])
def test_missing_completion_is_error(book_path, open_book):
    with ProcessingContext() as context:
        if open_book:
            context.open_epub(book_path).verify(OPFPath())
    assert context.result is not None
    assert context.result.error == EpubErrorReason.UNKNOWN
    assert "without succeed" in context.result.details
    if open_book:
        assert isinstance(context.epub.source, ZipFileSource)
        assert context.epub.source._zip_file is None
    else:
        assert context.result.original_epub is None
        assert context.result.input_path is None


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("phase", ["opening", "processing"])
def test_interrupts_propagate_and_release_source(book_path, monkeypatch, interrupt, phase):
    handles = []
    original_info = EPUB.info

    def read_info(epub):
        handles.append(epub.source.zip_file)
        if phase == "opening":
            raise interrupt()
        return original_info(epub)

    monkeypatch.setattr(EPUB, "info", read_info)
    with pytest.raises(interrupt):
        with ProcessingContext() as context:
            context.open_epub(book_path)
            raise interrupt()
    assert len(handles) == 1
    assert handles[0].fp is None
    assert context.result is None


@pytest.mark.parametrize("later_failure", ["error", "skip"])
def test_failure_after_success_marking_wins(book_path, tmp_path, later_failure):
    with ProcessingContext() as context:
        context.open_epub(book_path)
        destination = tmp_path / "output.epub"
        context.epub.package_into(destination)
        context.succeed(EPUB(destination).info())
        if later_failure == "error":
            raise RuntimeError("Post-export failure")
        context.verify(SerenePanda())
    assert context.result is not None
    assert not context.result.success
    assert context.result.new_epub is None
    assert context.result.error if later_failure == "error" else context.result.skip


@pytest.mark.parametrize("body_failure", [None, ValueError, KeyboardInterrupt])
def test_cleanup_failure_preserves_body_error_or_interrupt(book_path, monkeypatch, body_failure):
    original_open = ZipFileSource.open
    handles = []

    @contextmanager
    def failing_cleanup(source):
        # Only the owning scope fails; nested metadata reads borrow its handle.
        owns_handle = source._zip_file is None
        try:
            with original_open(source) as opened:
                if owns_handle:
                    handles.append(source.zip_file)
                yield opened
        finally:
            if owns_handle:
                raise OSError("Close failed")

    monkeypatch.setattr(ZipFileSource, "open", failing_cleanup)

    context = ProcessingContext()

    def process():
        with context:
            context.open_epub(book_path)
            if body_failure is not None:
                raise body_failure("Body failed")

    if body_failure is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt, match="Body failed"):
            process()
        assert context.result is None
    else:
        process()
        assert context.result is not None
        assert context.result.error == EpubErrorReason.UNKNOWN
        assert "Close failed" in context.result.details
        if body_failure is not None:
            assert "Body failed" in context.result.details
    assert len(handles) == 1
    assert handles[0].fp is None


@pytest.mark.parametrize("action", ["access", "verify", "succeed"])
def test_book_must_be_open_before_use(book_path, action):
    info = EPUB(book_path).info()
    with ProcessingContext() as context:
        if action == "access":
            _ = context.epub
        elif action == "verify":
            context.verify(OPFPath())
        else:
            context.succeed(info)
        pytest.fail("Used the context without opening a book")
    assert context.result is not None
    assert context.result.error == EpubErrorReason.UNKNOWN
    assert "open_epub" in context.result.details
    assert context.result.original_epub is None


def test_second_book_cannot_replace_first(book_path, tmp_path):
    with ProcessingContext() as context:
        context.open_epub(book_path)
        assert isinstance(context.epub.source, ZipFileSource)
        handle = context.epub.source.zip_file
        context.open_epub(tmp_path / "other.epub")
        pytest.fail("A second book was opened")
    assert context.result is not None
    assert "only open one book" in context.result.details
    assert context.result.input_path == str(book_path)
    assert context.result.original_epub is not None
    assert context.result.original_epub.path == book_path
    assert handle.fp is None


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"success": True, "skip": EpubSkipReason.NOT_IMPLEMENTED},
        {"success": True, "error": EpubErrorReason.UNKNOWN},
        {"skip": EpubSkipReason.NOT_IMPLEMENTED, "error": EpubErrorReason.UNKNOWN},
        {"success": True},
    ],
)
def test_manual_outcome_requires_one_status_and_output_info(arguments):
    with pytest.raises(ValueError):
        ProcessingContext().outcome(**arguments)


def test_runs_are_constructible_and_reportable(book_path, capsys):
    info = EPUB(book_path).info()
    outcome = ProcessingRun(skip=EpubSkipReason.NOT_IMPLEMENTED, original_epub=info)
    assert outcome.analytics == []
    assert outcome.input_path is None
    outcome.report()
    outcome.short_report()
    assert book_path.name in capsys.readouterr().out
