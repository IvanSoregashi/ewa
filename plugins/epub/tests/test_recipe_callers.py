import importlib
import sys
from concurrent.futures import Future
from types import ModuleType

import pytest
from typer.testing import CliRunner

from epub.errors import EpubSkipReason
from epub.processing_run import ProcessingRun
from library.epub.epub import EpubInfo
from test_recipe_run import recipe as recipe, write_book


@pytest.fixture
def cli(recipe, monkeypatch):
    # The unrelated file-moving module imports real application configuration.
    orchestration = ModuleType("epub.serene_panda.orchestration")
    setattr(orchestration, "move_file_preserving_hierarchy", lambda *args: pytest.fail("Unexpected file move"))
    monkeypatch.setitem(sys.modules, "epub.serene_panda.orchestration", orchestration)
    monkeypatch.delitem(sys.modules, "epub.main", raising=False)
    module = importlib.import_module("epub.main")
    yield module
    sys.modules.pop("epub.main", None)


@pytest.mark.parametrize("reason", ["directory", "destination"])
def test_decrypt_filters_without_processing_or_analytics(recipe, cli, tmp_path, monkeypatch, reason):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    destination = recipe.settings.decrypted_epub_dir / path.name
    if reason == "directory":
        path = tmp_path / "outside.epub"
        path.write_bytes(b"not parsed")
    else:
        destination.parent.mkdir()
        destination.write_bytes(b"existing destination")
    original = path.read_bytes()

    def unexpected(*args, **kwargs):
        pytest.fail("Filtered paths must not be processed or recorded")

    monkeypatch.setattr(recipe, "_fully_process_encrypted_panda", unexpected)
    monkeypatch.setattr(recipe, "_fully_process_encrypted_panda_with_context", unexpected)
    monkeypatch.setattr(recipe.recipe_analytics, "record_analytics", unexpected)
    monkeypatch.setattr(recipe, "fully_process_encrypted_panda", unexpected)
    cli.decrypt(path)
    assert path.read_bytes() == original
    if reason == "destination":
        assert destination.read_bytes() == b"existing destination"


@pytest.mark.parametrize("dry_run", [False, True])
def test_decrypt_dispatches_eligible_path_once(recipe, cli, monkeypatch, dry_run):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    run = ProcessingRun(input_path=str(path), skip=EpubSkipReason.NOT_IMPLEMENTED)
    processed = []
    reported = []

    def process(value, **kwargs):
        processed.append((value, kwargs))
        return run

    monkeypatch.setattr(recipe, "fully_process_encrypted_panda", process)
    monkeypatch.setattr(ProcessingRun, "report", lambda result: reported.append(result))
    cli.decrypt(path, dry_run=dry_run)
    assert processed == [(str(path), {"dry_run": dry_run})]
    assert reported == [run]


@pytest.mark.parametrize("dry_run", [False, True])
def test_single_caller_uses_legacy_and_records_only_its_result(recipe, monkeypatch, dry_run):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    run = ProcessingRun(input_path=str(path), skip=EpubSkipReason.NOT_IMPLEMENTED)
    calls = []

    def legacy(value, **kwargs):
        assert value == str(path)
        assert kwargs == {"dry_run": dry_run}
        return run

    def candidate(*args):
        pytest.fail("Candidate must not silently replace the legacy recipe")

    monkeypatch.setattr(recipe, "_fully_process_encrypted_panda", legacy)
    monkeypatch.setattr(recipe, "_fully_process_encrypted_panda_with_context", candidate)
    monkeypatch.setattr(recipe.recipe_analytics, "record_analytics", lambda rows, url: calls.append((rows, url)))
    assert recipe.fully_process_encrypted_panda(str(path), dry_run=dry_run) is run
    assert calls == [([run], recipe.settings.database_url)]


@pytest.mark.parametrize("max_workers", [0, 2])
@pytest.mark.parametrize("has_eligible", [False, True])
@pytest.mark.parametrize("dry_run", [False, True])
def test_batch_filters_before_synchronous_work_or_pool_submission(
    recipe, tmp_path, monkeypatch, max_workers, has_eligible, dry_run
):
    batch = importlib.import_module("epub.recipe_epubs")
    blocked = write_book(recipe.settings.encrypted_epub_dir / "blocked.epub")
    destination = recipe.settings.decrypted_epub_dir / blocked.name
    destination.parent.mkdir()
    destination.write_bytes(b"existing destination")
    outside = tmp_path / "outside.epub"
    outside.write_bytes(b"not parsed")
    eligible = recipe.settings.encrypted_epub_dir / "eligible.epub"
    if has_eligible:
        write_book(eligible)
    run = ProcessingRun(input_path=str(eligible), skip=EpubSkipReason.NOT_IMPLEMENTED)
    processed = []
    recorded = []
    submitted = []
    pools = []

    def legacy(path, **kwargs):
        assert kwargs == {"dry_run": dry_run}
        processed.append(path)
        return run

    class ImmediatePool:
        def __init__(self, **kwargs):
            pools.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, path, **kwargs):
            assert function is legacy
            assert kwargs == {"dry_run": dry_run}
            submitted.append(path)
            future = Future()
            future.set_result(function(path, **kwargs))
            return future

    monkeypatch.setattr(batch, "_fully_process_encrypted_panda", legacy)
    monkeypatch.setattr(batch, "ProcessPoolExecutor", ImmediatePool)
    monkeypatch.setattr(batch, "record_analytics", lambda rows, url: recorded.append(list(rows)))
    results = batch.fully_process_encrypted_pandas(tmp_path, max_workers=max_workers, flush_size=1, dry_run=dry_run)
    assert results == ([run] if has_eligible else [])
    assert processed == ([str(eligible)] if has_eligible else [])
    assert recorded == ([[run]] if has_eligible else [])
    assert submitted == ([str(eligible)] if has_eligible and max_workers else [])
    assert pools == ([{"max_workers": max_workers}] if has_eligible and max_workers else [])
    assert destination.read_bytes() == b"existing destination"
    assert outside.read_bytes() == b"not parsed"


@pytest.mark.parametrize("command", ["decrypt", "dd"])
@pytest.mark.parametrize("flag", [None, "-d", "--dry_run"])
def test_cli_dry_run_flags_and_default(recipe, cli, monkeypatch, command, flag):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    destination = recipe.settings.decrypted_epub_dir / path.name
    destination.parent.mkdir()
    destination.write_bytes(b"output owned by the recipe")
    run = ProcessingRun(success=True, new_epub=EpubInfo.from_path(destination))
    calls = []

    def process(*args, **kwargs):
        calls.append((args, kwargs))
        return run if command == "decrypt" else [run]

    monkeypatch.setattr(recipe, "should_process_path", lambda value: True)
    monkeypatch.setattr(recipe, "fully_process_encrypted_panda", process)
    monkeypatch.setattr(cli.recipe_epubs, "fully_process_encrypted_pandas", process)
    monkeypatch.setattr(ProcessingRun, "report", lambda result: None)
    argument = path if command == "decrypt" else path.parent
    arguments = [command, str(argument)] + ([flag] if flag else [])
    result = CliRunner().invoke(cli.app, arguments)
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0][1]["dry_run"] is (flag is not None)
    assert destination.read_bytes() == b"output owned by the recipe"
