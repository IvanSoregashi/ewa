import importlib
from concurrent.futures import Future

import pytest

from epub.errors import EpubSkipReason
from epub.processing_run import ProcessingRun
from test_recipe_run import recipe as recipe, write_book


@pytest.mark.parametrize("reason", ["directory", "destination"])
def test_single_caller_filters_without_processing_or_analytics(recipe, tmp_path, monkeypatch, reason):
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
    assert recipe.fully_process_encrypted_panda(str(path)) is None
    assert path.read_bytes() == original
    if reason == "destination":
        assert destination.read_bytes() == b"existing destination"


def test_single_caller_uses_legacy_and_records_only_its_result(recipe, monkeypatch):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    run = ProcessingRun(input_path=str(path), skip=EpubSkipReason.NOT_IMPLEMENTED)
    calls = []

    def legacy(value):
        assert value == str(path)
        return run

    def candidate(*args):
        pytest.fail("Candidate must not silently replace the legacy recipe")

    monkeypatch.setattr(recipe, "_fully_process_encrypted_panda", legacy)
    monkeypatch.setattr(recipe, "_fully_process_encrypted_panda_with_context", candidate)
    monkeypatch.setattr(recipe.recipe_analytics, "record_analytics", lambda rows, url: calls.append((rows, url)))
    assert recipe.fully_process_encrypted_panda(str(path)) is run
    assert calls == [([run], recipe.settings.database_url)]


@pytest.mark.parametrize("max_workers", [0, 2])
@pytest.mark.parametrize("has_eligible", [False, True])
def test_batch_filters_before_synchronous_work_or_pool_submission(
    recipe, tmp_path, monkeypatch, max_workers, has_eligible
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

    def legacy(path):
        processed.append(path)
        return run

    class ImmediatePool:
        def __init__(self, **kwargs):
            pools.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, path):
            assert function is legacy
            submitted.append(path)
            future = Future()
            future.set_result(function(path))
            return future

    monkeypatch.setattr(batch, "_fully_process_encrypted_panda", legacy)
    monkeypatch.setattr(batch, "ProcessPoolExecutor", ImmediatePool)
    monkeypatch.setattr(batch, "record_analytics", lambda rows, url: recorded.append(list(rows)))
    results = batch.fully_process_encrypted_pandas(tmp_path, max_workers=max_workers, flush_size=1)
    assert results == ([run] if has_eligible else [])
    assert processed == ([str(eligible)] if has_eligible else [])
    assert recorded == ([[run]] if has_eligible else [])
    assert submitted == ([str(eligible)] if has_eligible and max_workers else [])
    assert pools == ([{"max_workers": max_workers}] if has_eligible and max_workers else [])
    assert destination.read_bytes() == b"existing destination"
    assert outside.read_bytes() == b"not parsed"
