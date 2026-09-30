from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
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
        referenced=True,
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
    assert run.analytics[0].success
    assert run.analytics[0].original_image.path == "cover.png"
    assert run.analytics[0].new_image.path == "cover.jpg"
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
            assert "cover.jpg" in archive.namelist() and "cover.png" not in archive.namelist()
            assert b'src="cover.jpg"' in archive.read("chapter.xhtml")
            package = archive.read("OEBPS/package.opf")
            assert b'href="../cover.jpg"' in package and b'media-type="image/jpeg"' in package
            assert b"cover.png" not in package
            with Image.open(BytesIO(archive.read("cover.jpg"))) as image:
                image.load()
                assert image.format == "JPEG"
            assert not any(name.lower().endswith("serenepanda.ttf") for name in archive.namelist())


@pytest.mark.parametrize("command", ["decrypt-no-relink", "dd-nr"])
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
        else [((), {"directory": path.parent, "flush_size": 8, "dry_run": flag is not None})]
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


@pytest.mark.parametrize("dry_run", [False, True])
def test_alternative_recipe_reports_unmatched_conversion(recipe, dry_run):
    path = write_book(
        recipe.settings.encrypted_epub_dir / "orphan.epub",
        opf_path="OEBPS/package.opf",
        fonts=("fonts/SerenePanda.ttf", "other/SerenePanda.ttf"),
        referenced=False,
    )
    original = path.read_bytes()
    run = recipe._process_encrypted_panda_no_relink(str(path), dry_run=dry_run)
    assert run.success and run.skip is None
    assert len(run.analytics) == 1 and run.analytics[0].success
    report = recipe.settings.profile_dir / "epub/unmatched_links/orphan.json"
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "unmatched_links": {"cover.png": "cover.jpg"},
        "unmatched_manifest_links": {},
    }
    processed = recipe.settings.processed_epub_dir / path.name
    assert (path if dry_run else processed).read_bytes() == original
    assert path.exists() == dry_run
    assert (recipe.settings.decrypted_epub_dir / path.name).exists() == (not dry_run)
    assert processed.exists() == (not dry_run)


@pytest.mark.parametrize("dry_run", [False, True])
def test_alternative_recipe_rejects_image_rename_collision(recipe, dry_run):
    path = write_book(recipe.settings.encrypted_epub_dir / "collision.epub", opf_path="OEBPS/package.opf")
    with ZipFile(path, "a") as archive:
        archive.writestr("cover.jpg", b"existing resource")
    original = path.read_bytes()
    run = recipe._process_encrypted_panda_no_relink(str(path), dry_run=dry_run)
    assert run.error == EpubErrorReason.UNKNOWN and not run.success
    assert path.read_bytes() == original
    assert not (recipe.settings.decrypted_epub_dir / path.name).exists()
    assert not (recipe.settings.processed_epub_dir / path.name).exists()


def test_alternative_recipe_reports_manifest_only_misses(recipe):
    from lxml import etree

    path = write_book(recipe.settings.encrypted_epub_dir / "missing-manifest.epub")
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    package = etree.fromstring(files["content.opf"])
    item = package.xpath("//*[local-name()='item'][@href='cover.png']")[0]
    item.getparent().remove(item)
    files["content.opf"] = etree.tostring(package)
    with ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    run = recipe._process_encrypted_panda_no_relink(str(path), dry_run=True)
    assert run.success
    report = recipe.settings.profile_dir / "epub/unmatched_links/missing-manifest.json"
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "unmatched_links": {},
        "unmatched_manifest_links": {"cover.png": "cover.jpg"},
    }


def test_clean_retry_removes_previous_unmatched_report(recipe):
    path = write_book(recipe.settings.encrypted_epub_dir / "retry.epub", referenced=False)
    report = recipe.settings.profile_dir / "epub/unmatched_links/retry.json"
    assert recipe._process_encrypted_panda_no_relink(str(path), dry_run=True).success
    assert report.exists()
    write_book(path, referenced=True)
    assert recipe._process_encrypted_panda_no_relink(str(path), dry_run=True).success
    assert not report.exists()


def test_report_write_failure_does_not_block_processing(recipe, monkeypatch, caplog):
    path = write_book(recipe.settings.encrypted_epub_dir / "orphan.epub", referenced=False)
    write_text = Path.write_text

    def fail_report_write(path, *args, **kwargs):
        if "unmatched_links" in path.parts:
            raise PermissionError("Report directory is read-only")
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report_write)
    run = recipe._process_encrypted_panda_no_relink(str(path), dry_run=True)
    assert run.success
    assert "Could not update unmatched-link report" in caplog.text
    assert path.exists()


def test_spawned_reports_keep_same_named_books_separate(recipe, batch):
    root = recipe.settings.encrypted_epub_dir
    for folder in ("first", "second"):
        parent = root / folder
        parent.mkdir()
        write_book(parent / "book.epub", referenced=False)
    runs = batch.process_encrypted_pandas_no_relink(root, max_workers=2, flush_size=1, dry_run=True)
    assert len(runs) == 2 and all(run.success for run in runs)
    reports = recipe.settings.profile_dir / "epub/unmatched_links"
    assert sorted(path.relative_to(reports).as_posix() for path in reports.rglob("*.json")) == [
        "first/book.json",
        "second/book.json",
    ]
    for report in reports.rglob("*.json"):
        assert json.loads(report.read_text(encoding="utf-8")) == {
            "unmatched_links": {"cover.png": "cover.jpg"},
            "unmatched_manifest_links": {},
        }
