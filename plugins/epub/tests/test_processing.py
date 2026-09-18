import io
import pickle
from zipfile import ZipFile

import pytest
from sqlalchemy import inspect
from sqlmodel import Field, SQLModel

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.processing import ProcessingContext
from epub.protocols import VerificationResult
from epub.results import EpubOperationResult
from library.epub.epub import EPUB
from library.epub.resources import Resource, ResourceIndex


class ProcessingTestRecord(SQLModel, table=True):
    """Synthetic operation analytics; no engine or table creation is needed."""

    __tablename__ = "processing_context_test_records"

    id: int | None = Field(default=None, primary_key=True)
    description: str


@pytest.fixture
def context(tmp_path):
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
    epub = EPUB(path)
    return ProcessingContext(epub=epub, original_epub=epub.info())


def test_contexts_have_independent_working_state(context):
    other_epub = EPUB(context.epub.path)
    other = ProcessingContext(epub=other_epub, original_epub=other_epub.info())
    context.replacements["cover.png"] = "cover.webp"
    context.findings.append(VerificationResult(True, "First book checked"))
    context.analytics.append(ProcessingTestRecord(description="First book edited"))
    context.epub.resources.by_path("chapter.xhtml").content = b"edited"

    assert other.replacements == {}
    assert other.findings == []
    assert other.analytics == []
    assert b"Original" in other.epub.resources.by_path("chapter.xhtml").content


@pytest.mark.parametrize("status", ["success", "skip", "error"])
def test_outcomes_preserve_evidence_without_live_resources(context, tmp_path, status):
    finding = VerificationResult(True, "Chapter parsed before editing")
    record = ProcessingTestRecord(description="Chapter edited")
    context.findings.append(finding)
    context.analytics.append(record)
    chapter = context.epub.resources.by_path("chapter.xhtml")
    chapter.content = b"<html><body>Edited</body></html>"
    context.replacements["cover.png"] = "cover.webp"

    arguments = {"details": "Final diagnosis"}
    if status == "success":
        destination = tmp_path / "result.epub"
        context.epub.package_into(destination)
        arguments.update(success=True, new_epub=EPUB(destination).info())
    elif status == "skip":
        context.findings.append(VerificationResult(False, "Links unmatched"))
        arguments.update(skip=EpubSkipReason.UNMATCHED_LINKS)
    else:
        try:
            raise RuntimeError("Later operation failed")
        except RuntimeError as exc:
            arguments.update(error=EpubErrorReason.UNKNOWN, details=str(exc))

    class OutcomePickler(pickle.Pickler):
        def persistent_id(self, obj):
            assert not isinstance(obj, (ProcessingContext, EPUB, Resource, ResourceIndex, type(context.epub.source)))
            return None

    # Traverse the serialized graph while the source is open, so accidentally
    # returning a live object cannot hide behind a closed source handle.
    with context.epub.keep_open():
        outcome = context.outcome(**arguments)
        buffer = io.BytesIO()
        OutcomePickler(buffer).dump(outcome)
    restored = pickle.loads(buffer.getvalue())

    assert isinstance(outcome, EpubOperationResult)
    assert outcome.success == (status == "success")
    assert outcome.skip == (EpubSkipReason.UNMATCHED_LINKS if status == "skip" else None)
    assert outcome.error == (EpubErrorReason.UNKNOWN if status == "error" else None)
    assert outcome.original_epub == context.original_epub
    assert outcome.original_epub.title == "Synthetic book"
    assert outcome.new_epub == arguments.get("new_epub")
    assert outcome.details == arguments["details"]
    assert outcome.findings == restored.findings == context.findings
    assert restored.analytics[0].description == record.description
    assert outcome.analytics == [record]
    assert inspect(record).transient
    assert inspect(record).session is None
    assert record.id is None
    assert b"Edited" in chapter.content  # No rollback on skip/error.
    assert context.replacements == {"cover.png": "cover.webp"}
    assert not hasattr(restored, "replacements")

    context.findings.clear()
    context.analytics.clear()
    assert outcome.findings[0] == finding
    assert outcome.analytics == [record]


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
def test_outcome_requires_one_status_and_output_info_for_success(context, arguments):
    with pytest.raises(ValueError):
        context.outcome(**arguments)


def test_legacy_results_remain_constructible(context):
    outcome = EpubOperationResult(skip=EpubSkipReason.NOT_IMPLEMENTED, original_epub=context.original_epub)
    assert outcome.findings == []
    assert outcome.analytics == []
    assert outcome.image_results == []
