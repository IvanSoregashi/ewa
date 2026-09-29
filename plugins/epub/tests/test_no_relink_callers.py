import os
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlmodel import Session, select
from typer.testing import CliRunner

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.image_analytics import ImageOptimizationRecord
from epub.processing_run import ProcessingRun
from library.database.sqlite_model_table import get_engine
from test_recipe_batch import batch as batch
from test_recipe_callers import cli as cli
from test_recipe_run import recipe as recipe, write_book


@pytest.mark.parametrize("caller", ["single", "sync", "default", "spawn"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_no_relink_callers_process_and_persist(recipe, batch, tmp_path, caller, dry_run):
    root = recipe.settings.encrypted_epub_dir
    path = write_book(
        root / "success.epub",
        fonts=("fonts/SerenePanda.ttf", "other/SerenePanda.ttf"),
        opf_path="OEBPS/package.opf",
        referenced=False,
    )
    original = path.read_bytes()
    if caller == "single":
        runs = [recipe.process_encrypted_panda_no_relink(str(path), dry_run=dry_run)]
    else:
        skip = write_book(root / "skip.epub", fonts=())
        error = root / "error.epub"
        error.write_bytes(b"invalid archive")
        blocked = root / "blocked.epub"
        blocked.write_bytes(b"existing destination must filter this input")
        blocked_output = recipe.settings.decrypted_epub_dir / blocked.name
        blocked_output.parent.mkdir()
        blocked_output.write_bytes(b"existing output")
        workers = {"sync": 0, "default": None, "spawn": 2}[caller]
        runs = batch.process_encrypted_pandas_no_relink(root, max_workers=workers, flush_size=2, dry_run=dry_run)
        assert len(runs) == 3
        by_name = {Path(run.input_path).name: run for run in runs}
        assert by_name[skip.name].skip == EpubSkipReason.SERENE_PANDA_FONT
        assert by_name[error.name].error == EpubErrorReason.UNKNOWN
        assert skip.exists() and error.exists() and blocked.exists()
        assert blocked_output.read_bytes() == b"existing output"
        if caller == "spawn":
            markers = list((tmp_path / "workers").iterdir())
            assert markers and all(int(marker.name) != os.getpid() for marker in markers)

    run = next(run for run in runs if Path(run.input_path).name == path.name)
    assert run.success, run.details
    assert len(run.analytics) == 1
    assert run.analytics[0].original_image.path == "cover.png"
    with Session(get_engine(recipe.settings.database_url)) as session:
        assert len(session.exec(select(ProcessingRun)).all()) == len(runs)
        for returned in runs:
            stored = session.get(ProcessingRun, returned.id)
            assert stored is not None and stored.model_dump() == returned.model_dump()
        images = session.exec(select(ImageOptimizationRecord)).all()
        assert [image.model_dump() for image in images] == [image.model_dump() for image in run.analytics]

    output = recipe.settings.decrypted_epub_dir / path.name
    processed = recipe.settings.processed_epub_dir / path.name
    assert path.exists() == dry_run
    assert output.exists() == (not dry_run)
    assert processed.exists() == (not dry_run)
    assert (path if dry_run else processed).read_bytes() == original
    if not dry_run:
        with ZipFile(output) as archive:
            assert archive.testzip() is None
            assert "cover.png" in archive.namelist() and "cover.jpg" not in archive.namelist()
            assert "OEBPS/package.opf" in archive.namelist()
            assert not any(name.lower().endswith("serenepanda.ttf") for name in archive.namelist())


@pytest.mark.parametrize("command", ["decrypt-no-relink", "dd-no-relink"])
@pytest.mark.parametrize("flag", [None, "-d", "--dry_run"])
def test_no_relink_cli_dispatches_and_forwards_dry_run(recipe, cli, monkeypatch, command, flag):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    run = ProcessingRun(input_path=str(path), skip=EpubSkipReason.NOT_IMPLEMENTED)
    calls = []
    reported = []
    single = command == "decrypt-no-relink"

    def process(*args, **kwargs):
        calls.append((args, kwargs))
        return run if single else [run]

    def wrong_recipe(*args, **kwargs):
        pytest.fail("No-relink command dispatched the original recipe")

    monkeypatch.setattr(recipe, "fully_process_encrypted_panda", wrong_recipe)
    monkeypatch.setattr(cli.recipe_epubs, "fully_process_encrypted_pandas", wrong_recipe)
    monkeypatch.setattr(recipe, "process_encrypted_panda_no_relink", process)
    monkeypatch.setattr(cli.recipe_epubs, "process_encrypted_pandas_no_relink", process)
    monkeypatch.setattr(ProcessingRun, "report", lambda result: reported.append(result))
    args = [command, str(path if single else path.parent)] + ([flag] if flag else [])
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    assert reported == [run]
    assert calls == (
        [((str(path),), {"dry_run": flag is not None})]
        if single
        else [((), {"directory": path.parent, "max_workers": 8, "flush_size": 32, "dry_run": flag is not None})]
    )


@pytest.mark.parametrize("reason", ["directory", "destination"])
def test_no_relink_cli_filters_before_processing(recipe, cli, tmp_path, monkeypatch, reason):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    output = recipe.settings.decrypted_epub_dir / path.name
    if reason == "directory":
        path = tmp_path / "outside.epub"
        path.write_bytes(b"not parsed")
    else:
        output.parent.mkdir()
        output.write_bytes(b"existing output")

    def unexpected(*args, **kwargs):
        pytest.fail("Filtered path reached processing or persistence")

    monkeypatch.setattr(recipe, "process_encrypted_panda_no_relink", unexpected)
    monkeypatch.setattr(recipe.recipe_analytics, "record_analytics", unexpected)
    result = CliRunner().invoke(cli.app, ["decrypt-no-relink", str(path)])
    assert result.exit_code == 0, result.output
    assert path.exists()
    if reason == "destination":
        assert output.read_bytes() == b"existing output"
