import pickle
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational
from pydantic import ValidationError
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.image_analytics import ImageOptimizationRecord
from epub.processing_run import ProcessingRun
from epub.recipe_analytics import record_analytics
from library.asserts import require
from library.database.sqlite_model_table import get_engine
from library.epub.epub import EpubInfo
from library.epub.resources import IndexInfo
from library.image.constants import ImageFormat, ImageMode
from library.image.models import ImageInfo, ImageSkipReason


class ChapterMetric(SQLModel, table=True):
    __tablename__ = "test_chapter_metrics"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="epub_processing_runs.id")
    count: int


@pytest.fixture
def database(tmp_path):
    url = f"sqlite:///{tmp_path / 'analytics.sqlite'}"
    engine = get_engine(url)
    yield url, engine
    engine.dispose()


def make_run():
    run = ProcessingRun(
        skip=EpubSkipReason.NON_DEFAULT_OPF,
        details="A diagnostic worth retaining",
        input_path="book.epub",
        original_epub=EpubInfo(path=Path("book.epub"), path_size=200, images=IndexInfo(1, 100, 90)),
    )
    run.analytics.extend(
        [
            ImageOptimizationRecord(
                run_id=run.id,
                skip=ImageSkipReason.SMALL_IMAGE,
                original_image=ImageInfo(
                    path="cover.png", filesize=100, size=(8, 8), format=ImageFormat.PNG, mode=ImageMode.RGB
                ),
            ),
            ChapterMetric(run_id=run.id, count=3),
        ]
    )
    return run


@pytest.mark.parametrize("dpi", [(72, 96), (72.5, 96.25), (IFDRational(145, 2), IFDRational(385, 4))])
def test_image_dpi_serializes_and_round_trips_through_database(database, dpi):
    url, engine = database
    run = make_run()
    with Image.new("RGB", (8, 8)) as image:
        image.format = "JPEG"
        image.info["dpi"] = dpi
        info = ImageInfo.from_image(image, filesize=100)
    record = ImageOptimizationRecord(run_id=run.id, original_image=info, skip=ImageSkipReason.SMALL_IMAGE)
    run.analytics = [record]
    assert record.model_dump(mode="json")["original_image"]["dpi"] == [float(value) for value in dpi]
    record_analytics([run], url)
    with Session(engine) as session:
        stored = require(session.get(ImageOptimizationRecord, record.id))
        assert stored.original_image.dpi == tuple(float(value) for value in dpi)
        assert all(type(value) is float for value in require(stored.original_image.dpi))


def test_mixed_analytics_batch_directly_without_conversions(database):
    url, engine = database
    inserts = []
    commits = []

    @event.listens_for(engine, "before_cursor_execute")
    def track_inserts(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT"):
            inserts.append((statement.split()[2], executemany, len(parameters)))

    @event.listens_for(engine, "commit")
    def track_commit(connection):
        commits.append(len(inserts))

    runs = [make_run(), make_run(), make_run()]
    runs[1].skip = None
    runs[1].error = EpubErrorReason.UNKNOWN
    runs[2].skip = None
    runs[2].success = True
    runs[2].new_epub = runs[2].original_epub
    record_analytics(runs, url)

    assert inserts == [
        ("epub_processing_runs", True, 3),
        ("epub_image_optimizations", True, 3),
        ("test_chapter_metrics", True, 3),
    ]
    assert commits[-1] == 3
    assert all(count == 0 for count in commits[:-1])  # Schema creation precedes the single data transaction.
    for run in runs:
        assert inspect(run).detached
        assert run.details == "A diagnostic worth retaining"
        assert len(run.analytics) == 2
        assert all(inspect(row).detached for row in run.analytics)
    with Session(engine) as session:
        saved = require(session.get(ProcessingRun, runs[0].id))
        assert saved.original_epub == runs[0].original_epub
        assert isinstance(require(saved.original_epub).path, Path)
        assert isinstance(require(saved.original_epub).images, IndexInfo)
        image = session.exec(select(ImageOptimizationRecord)).first()
        assert require(image).original_image.format is ImageFormat.PNG
        assert require(image).original_image.mode is ImageMode.RGB
        assert require(image).original_image.size == (8, 8)
        assert saved.analytics == []
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT typeof(original_epub), typeof(new_epub) FROM epub_processing_runs WHERE id=:id"),
            {"id": runs[0].id.hex},
        ).one() == ("text", "null")


def test_failed_write_rolls_back_all_rows_and_retains_input(database):
    url, engine = database
    run = make_run()
    run.analytics[1].run_id = uuid4()  # An orphan must fail with SQLite foreign keys enabled.
    batch = [run]
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        record_analytics(batch, url)
    assert batch == [run]
    assert len(run.analytics) == 2
    assert inspect(run).transient
    with Session(engine) as session:
        assert session.exec(select(ProcessingRun)).all() == []
        assert session.exec(select(ImageOptimizationRecord)).all() == []
        assert session.exec(select(ChapterMetric)).all() == []


def test_replayed_transient_run_is_rejected_without_overwriting_history(database):
    url, engine = database
    run = make_run()
    replay = pickle.loads(pickle.dumps(run))
    record_analytics([run], url)
    replay.details = "Must not replace the original"
    with pytest.raises(IntegrityError, match="UNIQUE"):
        record_analytics([replay], url)
    with Session(engine) as session:
        assert require(session.get(ProcessingRun, run.id)).details == run.details
        assert len(session.exec(select(ImageOptimizationRecord)).all()) == 1


def test_invalid_stored_metadata_fails_validation(database):
    url, engine = database
    run = make_run()
    record_analytics([run], url)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE epub_processing_runs SET original_epub=:value"),
            {"value": '{"path":"book.epub","path_size":"invalid"}'},
        )
    with Session(engine) as session, pytest.raises(ValidationError):
        session.get(ProcessingRun, run.id)


def test_empty_batch_does_not_create_a_database(tmp_path):
    path = tmp_path / "unused.sqlite"
    record_analytics([], f"sqlite:///{path}")
    assert not path.exists()
