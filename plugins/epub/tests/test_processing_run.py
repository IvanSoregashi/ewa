import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from PIL import Image
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.image_analytics import ImageOptimizationRecord
from epub.processing import ProcessingContext
from epub.processing_run import ProcessingRun
from epub.recipe_analytics import record_analytics
from library.asserts import require
from library.epub.epub import EpubInfo
from library.image.constants import ImageFormat, ImageMode
from library.image.models import ImageErrorReason, ImageInfo, ImageOptimizationResult, ImageSkipReason
from processing_run_worker import process_book


RUN_TABLES = [SQLModel.metadata.tables[name] for name in ("epub_processing_runs", "epub_image_optimizations")]


@pytest.fixture
def book_path(tmp_path):
    path = tmp_path / "book.epub"
    image = BytesIO()
    Image.new("RGB", (8, 8)).save(image, format="PNG")
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("cover.png", image.getvalue())
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Run test</dc:title></metadata>'
            '<manifest><item id="cover" href="cover.png" media-type="image/png"/></manifest>'
            "<spine/></package>",
        )
    return path


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.sqlite'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine, tables=RUN_TABLES)
    yield engine
    engine.dispose()


def test_spawned_outcomes_and_evidence_persist_in_parent(book_path, engine):
    statuses = ["success", "skip", "error", "setup_error", "success"]
    # Explicit spawn also exercises Windows semantics when this test runs elsewhere.
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [
            pool.submit(
                process_book,
                book_path.with_name("missing.epub") if status == "setup_error" else book_path,
                status,
            )
            for status in statuses
        ]
        returned = [future.result(timeout=45) for future in futures]

    outcomes = [outcome for _, outcome in returned]
    assert all(pid != os.getpid() for pid, _ in returned)
    assert len({outcome.id for outcome in outcomes}) == len(outcomes)
    for status, outcome in zip(statuses, outcomes, strict=True):
        assert outcome.success == (status == "success")
        assert outcome.skip == (EpubSkipReason.NON_DEFAULT_OPF if status == "skip" else None)
        assert outcome.error == (EpubErrorReason.UNKNOWN if status in ("error", "setup_error") else None)
        assert len(outcome.analytics) == (0 if status == "setup_error" else 1)
        if status == "setup_error":
            assert outcome.original_epub is None
            assert outcome.input_path == str(book_path.with_name("missing.epub"))
        else:
            row = outcome.analytics[0]
            assert isinstance(row, ImageOptimizationRecord)
            assert row.run_id == outcome.id
            assert row.skip == ImageSkipReason.SMALL_IMAGE
            assert inspect(row).transient
            assert inspect(row).session is None

    record_analytics(outcomes, str(engine.url))
    assert all(outcome.input_path for outcome in outcomes)  # Still usable after the session closes.

    with Session(engine) as session:
        assert len(session.exec(select(ProcessingRun)).all()) == 5
        records = session.exec(select(ImageOptimizationRecord)).all()
        assert len(records) == 4
        for outcome in outcomes:
            run = require(session.get(ProcessingRun, outcome.id))
            assert (run.success, run.skip, run.error) == (outcome.success, outcome.skip, outcome.error)
            assert run.details == outcome.details
            assert run.analytics == []
            assert "analytics" not in run.model_dump()
            assert run.input_path == str(outcome.input_path)
            if outcome.original_epub is None:
                assert run.original_epub is None
            else:
                assert require(run.original_epub).title == "Run test"
                assert require(run.original_epub).path == book_path
                assert run.original_epub == outcome.original_epub
            if outcome.success:
                assert require(run.new_epub).path == require(outcome.new_epub).path
            else:
                assert run.new_epub is None
        assert {record.run_id for record in records} == {outcome.id for outcome in outcomes if outcome.analytics}


@pytest.mark.parametrize("status", ["success", "skip", "error"])
def test_image_schema_preserves_info_and_numeric_reasons(engine, status):
    context = ProcessingContext()
    original = ImageInfo(path="image.png", filesize=1200, size=(16, 32), format=ImageFormat.PNG, mode=ImageMode.RGB)
    new = ImageInfo(path="image.jpg", filesize=300, size=(16, 32), format=ImageFormat.JPEG, mode=ImageMode.RGB)
    if status == "success":
        result = ImageOptimizationResult(success=True, original_image=original, new_image=new)
    elif status == "skip":
        result = ImageOptimizationResult(skip=ImageSkipReason.WORSE_CONVERSION, original_image=original, new_image=new)
    else:
        result = ImageOptimizationResult(
            error=ImageErrorReason.DECODE_FAILED,
            original_image=ImageInfo.failed(path="image.png", filesize=1200),
        )
    row = ImageOptimizationRecord.from_result(context.run_id, result)
    context.analytics.append(row)
    outcome = context.outcome(error=EpubErrorReason.UNKNOWN, details="Book failed after image operation")
    record_analytics([outcome], str(engine.url))
    with Session(engine) as session:
        stored = session.exec(select(ImageOptimizationRecord)).one()
        assert (stored.success, stored.skip, stored.error) == (result.success, result.skip, result.error)
        assert stored.original_image.path == "image.png"
        assert stored.original_image.filesize == 1200
        assert stored.original_image.size == (None if status == "error" else (16, 32))
        assert stored.original_image.format == ("UNKNOWN" if status == "error" else "PNG")
        if status == "error":
            assert stored.original_image.width is None
            assert stored.original_image.height is None
            assert stored.original_image.bytes_per_pixel is None
            assert stored.new_image is None
        else:
            assert require(stored.new_image).path == "image.jpg"
            assert require(stored.new_image).format == "JPEG"


def test_database_rejects_orphan_analytics(engine):
    row = ImageOptimizationRecord(
        run_id=uuid4(), skip=ImageSkipReason.SMALL_IMAGE, original_image=ImageInfo.failed(path="image.png")
    )
    with Session(engine) as session:
        session.add(row)
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            session.commit()


def test_runs_without_opened_book_and_direct_construction(tmp_path):
    with ProcessingContext() as context:
        pass
    run = require(context.result)
    assert run.id == context.run_id
    assert run.input_path is None
    assert run.original_epub is None
    assert run.error == EpubErrorReason.UNKNOWN

    path = tmp_path / "legacy.epub"
    outcome = ProcessingRun(
        skip=EpubSkipReason.NOT_IMPLEMENTED, input_path=str(path), original_epub=EpubInfo(path=path, path_size=10)
    )
    assert outcome.input_path == str(path)
    assert require(outcome.original_epub).path_size == 10


def test_new_tables_leave_legacy_history_unchanged(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing.sqlite'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE successful_epubs (id INTEGER PRIMARY KEY, path TEXT)"))
        connection.execute(text("INSERT INTO successful_epubs VALUES (17, 'old.epub')"))
        before = connection.execute(text("SELECT sql FROM sqlite_master WHERE name='successful_epubs'")).scalar()
    SQLModel.metadata.create_all(engine, tables=RUN_TABLES)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT * FROM successful_epubs")).all() == [(17, "old.epub")]
        assert (
            connection.execute(text("SELECT sql FROM sqlite_master WHERE name='successful_epubs'")).scalar() == before
        )
    engine.dispose()
