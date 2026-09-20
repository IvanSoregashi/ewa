import importlib
import sys
from contextlib import contextmanager
from io import BytesIO
from types import ModuleType, SimpleNamespace
from zipfile import ZipFile

import pytest
from PIL import Image

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.image_analytics import ImageOptimizationRecord
from epub.processing_run import ProcessingRun
from epub.verification import OPFPath
from library.asserts import require
from library.epub.epub import EPUB


@pytest.fixture
def recipe(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        encrypted_epub_dir=tmp_path / "input",
        decrypted_epub_dir=tmp_path / "output",
        processed_epub_dir=tmp_path / "processed",
        serene_panda_dir=tmp_path / "dictionary",
        database_url=f"sqlite:///{tmp_path / 'analytics.sqlite'}",
    )
    settings.encrypted_epub_dir.mkdir()
    settings.serene_panda_dir.mkdir()
    (settings.serene_panda_dir / "translator.json").write_text("{}")
    config = ModuleType("epub.config")
    setattr(config, "settings", settings)
    monkeypatch.setitem(sys.modules, "epub.config", config)
    for name in ("epub.recipe_epub", "epub.recipe_epubs"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    recipe = importlib.import_module("epub.recipe_epub")
    yield recipe
    for name in ("epub.recipe_epub", "epub.recipe_epubs"):
        sys.modules.pop(name, None)


@pytest.fixture
def book_path(recipe):
    path = recipe.settings.encrypted_epub_dir / "book.epub"
    image = BytesIO()
    Image.new("RGB", (8, 8)).save(image, format="PNG")
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("cover.png", image.getvalue())
        archive.writestr("fonts/SerenePanda.ttf", b"font")
        archive.writestr("chapter.xhtml", "<html><body>Text</body></html>")
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Recipe test</dc:title></metadata>'
            '<manifest><item id="cover" href="cover.png" media-type="image/png"/>'
            '<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="font" href="fonts/SerenePanda.ttf" media-type="font/ttf"/></manifest>'
            '<spine><itemref idref="chapter"/></spine></package>',
        )
    return path


@pytest.mark.parametrize("failure", [None, "translation", "output_validation", "unmatched_links"])
def test_panda_recipe_returns_run_and_retains_image_evidence(recipe, book_path, monkeypatch, failure):
    original = book_path.read_bytes()
    original_info = EPUB.info
    if failure == "translation":

        def fail_translation(*args):
            raise ValueError("Translation failed")

        monkeypatch.setattr(recipe.html_editing, "translate_text", fail_translation)
    elif failure == "output_validation":

        def fail_output_info(epub):
            if epub.path.parent == recipe.settings.decrypted_epub_dir:
                raise ValueError("Output invalid")
            return original_info(epub)

        monkeypatch.setattr(EPUB, "info", fail_output_info)
    elif failure == "unmatched_links":
        from library.image.models import ImageInfo, ImageOptimizationResult

        def renamed_image(*args, **kwargs):
            return ImageOptimizationResult(
                success=True,
                original_image=ImageInfo.failed(path="cover.png", filesize=100),
                new_image=ImageInfo.failed(path="cover.jpg", filesize=50),
            )

        monkeypatch.setattr(recipe.recipe_image, "perform_image_optimization", renamed_image)

    run = recipe._fully_process_encrypted_panda(str(book_path))
    assert isinstance(run, ProcessingRun)
    assert run.success == (failure is None)
    assert run.skip == (EpubSkipReason.UNMATCHED_LINKS if failure == "unmatched_links" else None)
    expected_error = {
        "translation": EpubErrorReason.UNKNOWN,
        "output_validation": EpubErrorReason.INCORRECT_RESULT,
    }.get(failure)
    assert run.error == expected_error
    assert require(run.original_epub).title == "Recipe test"
    assert len(run.analytics) == 1
    image = run.analytics[0]
    assert isinstance(image, ImageOptimizationRecord)
    assert image.run_id == run.id
    assert image.original_image.path == "cover.png"
    assert book_path.read_bytes() == original
    # Preserve the existing recipe's destination-deletion/original-movement scaffolding.
    assert not (recipe.settings.decrypted_epub_dir / book_path.name).exists()


def test_cleanup_error_overrides_pending_skip(recipe, book_path, monkeypatch):
    original_open = EPUB.keep_open
    depth = 0

    @contextmanager
    def fail_cleanup(epub):
        nonlocal depth
        depth += 1
        try:
            with original_open(epub) as opened:
                yield opened
            if depth == 1:
                raise OSError("Source cleanup failed")
        finally:
            depth -= 1

    monkeypatch.setattr(EPUB, "keep_open", fail_cleanup)
    monkeypatch.setattr(recipe, "OPFPath", lambda: OPFPath("unexpected.opf"))
    run = recipe._fully_process_encrypted_panda(str(book_path))
    assert run.skip is None
    assert run.error == EpubErrorReason.UNKNOWN
    assert "Source cleanup failed" in run.details


def test_batch_propagates_persistence_failure_without_clearing_buffer(recipe, book_path, monkeypatch):
    batch = importlib.import_module("epub.recipe_epubs")
    run = ProcessingRun(skip=EpubSkipReason.NOT_IMPLEMENTED, input_path=str(book_path))
    retained = []
    monkeypatch.setattr(batch, "_fully_process_encrypted_panda", lambda path: run)

    def fail_recording(buffer, url):
        retained.append(buffer)
        raise OSError("Database unavailable")

    monkeypatch.setattr(batch, "record_analytics", fail_recording)
    with pytest.raises(OSError, match="Database unavailable"):
        batch.fully_process_encrypted_pandas(recipe.settings.encrypted_epub_dir, max_workers=0, flush_size=1)
    assert len(retained) == 1
    assert retained[0] == [run]
