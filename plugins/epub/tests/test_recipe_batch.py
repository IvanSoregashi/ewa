import importlib
import multiprocessing
import os
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlmodel import Session, select

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.image_analytics import ImageOptimizationRecord
from epub.processing_run import ProcessingRun
from library.database.sqlite_model_table import get_engine
from recipe_batch_worker import forbid_worker_database, raise_in_worker, terminate_worker
from test_recipe_run import recipe as recipe, write_book


@pytest.fixture
def batch(recipe, tmp_path, monkeypatch):
    # Spawn imports real settings afresh; point them at the parent's temporary inputs.
    profile = tmp_path / "profile"
    dictionary = profile / "epub" / "serene_panda"
    dictionary.mkdir(parents=True)
    (dictionary / "translator.json").write_bytes((recipe.settings.serene_panda_dir / "translator.json").read_bytes())
    monkeypatch.setenv("PROFILE_DIR", str(profile))
    for name in ("encrypted_epub_dir", "decrypted_epub_dir", "processed_epub_dir"):
        monkeypatch.setenv(name.upper(), str(getattr(recipe.settings, name)))
    module = importlib.import_module("epub.recipe_epubs")
    markers = tmp_path / "workers"
    markers.mkdir()

    def spawn_pool(**kwargs):
        return ProcessPoolExecutor(
            **kwargs,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=forbid_worker_database,
            initargs=(markers,),
        )

    monkeypatch.setattr(module, "ProcessPoolExecutor", spawn_pool)
    return module


@pytest.mark.parametrize("dry_run", [False, True])
def test_spawn_matches_synchronous_outcomes_bytes_and_persistence(recipe, batch, tmp_path, monkeypatch, dry_run):
    root = recipe.settings.encrypted_epub_dir
    write_book(root / "success.epub")
    write_book(root / "skip.epub", referenced=False)
    error = write_book(root / "error.epub")
    with ZipFile(error, "a") as archive:
        archive.writestr("second.png", archive.read("cover.png"))
        archive.writestr("second.jpg", b"existing resource")
    # Preserve an existing container's timestamp instead of generating one per run.
    for path in root.glob("*.epub"):
        with ZipFile(path, "a") as archive:
            archive.writestr(
                "META-INF/container.xml",
                '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles></container>",
            )
    (root / "setup_error.epub").write_bytes(b"invalid archive")
    originals = {path: path.read_bytes() for path in root.glob("*.epub")}
    chunks = []
    record = batch.record_analytics

    def record_in_parent(runs, url):
        assert os.getpid() == parent_pid
        chunks.append(len(runs))
        record(runs, url)

    parent_pid = os.getpid()
    monkeypatch.setattr(batch, "record_analytics", record_in_parent)
    snapshots = []
    outputs = []
    for workers in (0, 2):
        runs = batch.fully_process_encrypted_pandas(root, max_workers=workers, flush_size=3, dry_run=dry_run)
        assert len(runs) == 4
        snapshots.append(
            {
                run.input_path: (
                    run.model_dump(mode="json", exclude={"id"}),
                    [image.model_dump(mode="json", exclude={"id", "run_id"}) for image in run.analytics],
                )
                for run in runs
            }
        )
        by_name = {Path(run.input_path).name: run for run in runs}
        assert by_name["success.epub"].success
        assert by_name["skip.epub"].skip == EpubSkipReason.UNMATCHED_LINKS
        for name in ("error.epub", "setup_error.epub"):
            assert by_name[name].error == EpubErrorReason.UNKNOWN
        assert {name: len(run.analytics) for name, run in by_name.items()} == {
            "success.epub": 1,
            "skip.epub": 1,
            "error.epub": 1,
            "setup_error.epub": 0,
        }
        with Session(get_engine(recipe.settings.database_url)) as session:
            for run in runs:
                stored = session.get(ProcessingRun, run.id)
                assert stored is not None and stored.model_dump() == run.model_dump()
                images = session.exec(
                    select(ImageOptimizationRecord).where(ImageOptimizationRecord.run_id == run.id)
                ).all()
                assert [image.model_dump() for image in images] == [image.model_dump() for image in run.analytics]
        output = recipe.settings.decrypted_epub_dir / "success.epub"
        outputs.append(output.read_bytes() if output.exists() else None)
        for path, original in originals.items():
            processed = recipe.settings.processed_epub_dir / path.name
            if processed.exists():
                assert processed.read_bytes() == original
                processed.rename(path)
            assert path.read_bytes() == original
        output.unlink(missing_ok=True)

    assert snapshots[0] == snapshots[1]
    assert outputs[0] == outputs[1]
    assert (outputs[0] is None) == dry_run
    assert chunks == [3, 1, 3, 1]
    pids = [int(path.name) for path in (tmp_path / "workers").iterdir()]
    assert pids and all(pid != parent_pid for pid in pids)


@pytest.mark.parametrize("workers,worker", [(2, raise_in_worker), (2, terminate_worker)])
def test_worker_failures_are_returned_and_persisted(recipe, batch, monkeypatch, workers, worker):
    root = recipe.settings.encrypted_epub_dir
    paths = [write_book(root / f"book-{index}.epub") for index in range(3)]
    originals = {path: path.read_bytes() for path in paths}
    monkeypatch.setattr(batch, "_fully_process_encrypted_panda", worker)
    runs = batch.fully_process_encrypted_pandas(root, max_workers=workers, flush_size=2, dry_run=True)
    assert {run.input_path for run in runs} == {str(path) for path in paths}
    for run in runs:
        assert run.error == EpubErrorReason.UNKNOWN
        assert not run.success and run.skip is None
        assert run.original_epub is None and run.new_epub is None and run.analytics == []
        assert ("BrokenProcessPool" if worker is terminate_worker else "RuntimeError") in run.details
    with Session(get_engine(recipe.settings.database_url)) as session:
        assert {run.id for run in session.exec(select(ProcessingRun)).all()} == {run.id for run in runs}
    assert all(path.read_bytes() == original for path, original in originals.items())


@pytest.mark.parametrize("workers", [0, None])
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_synchronous_dispatch_does_not_hide_unexpected_exceptions(recipe, batch, monkeypatch, workers, error_type):
    root = recipe.settings.encrypted_epub_dir
    write_book(root / "book.epub")

    def fail_worker(*args, **kwargs):
        raise error_type("Unexpected failure")

    monkeypatch.setattr(batch, "_fully_process_encrypted_panda", fail_worker)
    with pytest.raises(error_type, match="Unexpected failure"):
        batch.fully_process_encrypted_pandas(root, max_workers=workers, dry_run=True)
    assert not (root.parent / "analytics.sqlite").exists()


def test_submission_failure_does_not_discard_pending_results(recipe, batch, monkeypatch):
    root = recipe.settings.encrypted_epub_dir
    paths = [write_book(root / f"book-{index}.epub") for index in range(3)]
    first = ProcessingRun(input_path=str(paths[0]), skip=EpubSkipReason.NOT_IMPLEMENTED)

    class FailingPool:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, path, **kwargs):
            if path != str(paths[0]):
                raise BrokenProcessPool("Pool stopped accepting work")
            future = Future()
            future.set_result(first)
            return future

    monkeypatch.setattr(batch, "ProcessPoolExecutor", FailingPool)
    runs = batch.fully_process_encrypted_pandas(root, max_workers=2, flush_size=2)
    assert len(runs) == 3 and first in runs
    assert {run.input_path for run in runs} == {str(path) for path in paths}
    assert sum(run.error == EpubErrorReason.UNKNOWN for run in runs) == 2


def test_spawned_results_survive_parent_persistence_failure(recipe, batch, monkeypatch):
    root = recipe.settings.encrypted_epub_dir
    paths = [write_book(root / f"book-{index}.epub") for index in range(2)]
    retained = []

    def fail_recording(buffer, url):
        retained.append(buffer)
        raise OSError("Database unavailable")

    monkeypatch.setattr(batch, "record_analytics", fail_recording)
    with pytest.raises(OSError, match="Database unavailable"):
        batch.fully_process_encrypted_pandas(root, max_workers=2, flush_size=2, dry_run=True)
    assert len(retained) == 1 and len(retained[0]) == 2
    assert all(run.success and len(run.analytics) == 1 for run in retained[0])
    assert {run.input_path for run in retained[0]} == {str(path) for path in paths}
    assert not (root.parent / "analytics.sqlite").exists()
