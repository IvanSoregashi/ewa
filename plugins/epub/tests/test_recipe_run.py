import importlib
import random
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
from library.epub.media_type import EpubRole
from library.epub.utils_href import posix_relative_href


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


def write_book(path, *, referenced=True, fonts=("fonts/SerenePanda.ttf",), opf_path="content.opf"):
    image = BytesIO()
    with Image.frombytes("RGB", (256, 256), random.Random(0).randbytes(256 * 256 * 3)) as pixels:
        pixels.save(image, format="PNG")
    files = {
        "mimetype": b"application/epub+zip",
        "cover.png": image.getvalue(),
        "chapter.xhtml": (
            '<html><body>Text<img src="cover.png"/></body></html>' if referenced else "<html><body>Text</body></html>"
        ).encode(),
        "style.css": b'body { font-family: "SerenePanda", serif; }',
        "page_styles.css": b'@font-face { font-family: "SerenePanda"; src: url(fonts/SerenePanda.ttf); }',
        **{font: b"font" for font in fonts},
    }
    declarations = "".join(
        f'<item id="item{i}" href="{posix_relative_href(opf_path, name)}" media-type="{media_type}"/>'
        for i, (name, media_type) in enumerate(
            [
                ("chapter.xhtml", "application/xhtml+xml"),
                ("cover.png", "image/png"),
                ("style.css", "text/css"),
                ("page_styles.css", "text/css"),
                *((font, "font/ttf") for font in fonts),
            ]
        )
    )
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr(
            opf_path,
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Recipe test</dc:title></metadata>'
            f'<manifest>{declarations}</manifest><spine><itemref idref="item0"/></spine></package>',
        )
    return path


@pytest.fixture
def book_path(recipe):
    return write_book(recipe.settings.encrypted_epub_dir / "book.epub")


@pytest.mark.parametrize("failure", [None, "translation", "export", "output_validation", "unmatched_links"])
def test_panda_recipe_returns_run_and_retains_image_evidence(recipe, book_path, monkeypatch, failure):
    if failure == "unmatched_links":
        write_book(book_path, referenced=False)
    original = book_path.read_bytes()
    if failure == "translation":

        def fail_translation(*args):
            raise ValueError("Translation failed")

        monkeypatch.setattr(recipe.TextTranslator, "perform", fail_translation)
    elif failure == "export":

        def fail_export(epub, destination, **kwargs):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"unfinished output")
            raise OSError("Export failed")

        monkeypatch.setattr(EPUB, "package_into", fail_export)
    elif failure == "output_validation":
        original_info = EPUB.info

        def fail_output_info(epub):
            if epub.path.parent == recipe.settings.decrypted_epub_dir:
                raise ValueError("Output invalid")
            return original_info(epub)

        monkeypatch.setattr(EPUB, "info", fail_output_info)

    run = recipe._fully_process_encrypted_panda_with_context(str(book_path))
    assert isinstance(run, ProcessingRun)
    assert run.success == (failure is None)
    assert run.skip == (EpubSkipReason.UNMATCHED_LINKS if failure == "unmatched_links" else None)
    expected_error = {
        "translation": EpubErrorReason.UNKNOWN,
        "export": EpubErrorReason.UNKNOWN,
        "output_validation": EpubErrorReason.INCORRECT_RESULT,
    }.get(failure)
    assert run.error == expected_error
    assert require(run.original_epub).title == "Recipe test"
    assert (run.new_epub is not None) == (failure is None)
    assert len(run.analytics) == 1
    image = run.analytics[0]
    assert isinstance(image, ImageOptimizationRecord)
    assert image.success and image.run_id == run.id
    assert image.original_image.path == "cover.png"
    assert require(image.new_image).path == "cover.jpg"
    if failure == "unmatched_links":
        assert '"cover.png": "cover.jpg"' in run.details
    elif failure is not None:
        assert {"translation": "Translation failed", "export": "Export failed", "output_validation": "Output invalid"}[
            failure
        ] in run.details
    assert book_path.read_bytes() == original
    # Preserve the existing recipe's destination-deletion/original-movement scaffolding.
    assert not (recipe.settings.decrypted_epub_dir / book_path.name).exists()


def test_complete_recipe_exports_consistent_translated_book(recipe, book_path, monkeypatch, tmp_path):
    write_book(book_path, fonts=("fonts/SerenePanda.ttf", "other/SerenePanda.ttf"))
    original = book_path.read_bytes()
    monkeypatch.setattr(recipe, "sp_dictionary", str.maketrans({"T": "D"}))
    original_export = EPUB.package_into
    exported = []
    handles = []

    def capture_export(epub, destination, **kwargs):
        handles.append(epub.source.zip_file)
        assert handles[-1].fp is not None
        original_export(epub, destination, **kwargs)
        exported.append(destination.read_bytes())

    monkeypatch.setattr(EPUB, "package_into", capture_export)
    run = recipe._fully_process_encrypted_panda_with_context(str(book_path))
    assert run.success, run.details
    assert len(exported) == 1
    assert handles[0].fp is None
    review = tmp_path / "review.epub"
    review.write_bytes(exported[0])
    output = EPUB(review)
    assert b"Dext" in require(output.resources.by_path("chapter.xhtml")).content
    assert b"cover.jpg" in require(output.resources.by_path("chapter.xhtml")).content
    assert require(output.resources.by_path("style.css")).content == b"body { font-family: serif; }"
    assert require(output.resources.by_path("page_styles.css")).content == b""
    assert [font.filename for font in output.resources.by_role(EpubRole.FONT)] == ["other/SerenePanda.ttf"]
    assert output.package.manifest_item_by_path("fonts/SerenePanda.ttf") is None
    assert output.package.manifest_item_by_path("other/SerenePanda.ttf") is not None
    assert output.resources.by_path("cover.png") is None
    item = require(output.package.manifest_item_by_path("cover.jpg"))
    assert item.media_type == "image/jpeg"
    with Image.open(BytesIO(require(output.resources.by_path("cover.jpg")).content)) as image:
        assert image.format == "JPEG"
    assert require(run.new_epub).path == recipe.settings.decrypted_epub_dir / book_path.name
    assert require(run.new_epub).path_size == len(exported[0])
    assert book_path.read_bytes() == original
    assert not (recipe.settings.processed_epub_dir / book_path.name).exists()


@pytest.mark.parametrize("reason", ["opf", "font"])
def test_early_book_skips_do_not_optimize(recipe, book_path, monkeypatch, reason):
    if reason == "opf":
        write_book(book_path, opf_path="OEBPS/content.opf")
    else:
        write_book(book_path, fonts=())
    original = book_path.read_bytes()

    def unexpected_optimization(*args):
        pytest.fail("Early skip reached image optimization")

    monkeypatch.setattr(recipe.OptimizeImages, "perform", unexpected_optimization)
    run = recipe._fully_process_encrypted_panda_with_context(str(book_path))
    assert run.skip == {"opf": EpubSkipReason.NON_DEFAULT_OPF, "font": EpubSkipReason.SERENE_PANDA_FONT}[reason]
    assert not run.success and run.error is None
    assert run.analytics == []
    assert book_path.read_bytes() == original
    assert not (recipe.settings.decrypted_epub_dir / book_path.name).exists()


@pytest.mark.parametrize("failure", ["missing", "archive", "metadata"])
def test_setup_errors_become_outcomes(recipe, monkeypatch, failure):
    path = recipe.settings.encrypted_epub_dir / "broken.epub"
    if failure == "archive":
        path.write_bytes(b"invalid archive")
    elif failure == "metadata":
        with ZipFile(path, "w") as archive:
            archive.writestr("content.opf", "<broken")
    run = recipe._fully_process_encrypted_panda_with_context(str(path))
    assert run.error == EpubErrorReason.UNKNOWN
    assert not run.success and run.skip is None
    assert run.input_path == str(path)
    assert run.original_epub is None and run.new_epub is None
    assert run.analytics == []
    assert run.details


@pytest.mark.parametrize("phase", ["skip", "success", "output_validation"])
def test_cleanup_error_overrides_pending_outcome(recipe, book_path, monkeypatch, phase):
    original_open = EPUB.keep_open
    depth = 0

    @contextmanager
    def fail_cleanup(epub):
        nonlocal depth
        depth += 1
        try:
            with original_open(epub) as opened:
                yield opened
            if depth == 1 and epub.path == book_path:
                raise OSError("Source cleanup failed")
        finally:
            depth -= 1

    monkeypatch.setattr(EPUB, "keep_open", fail_cleanup)
    if phase == "skip":
        monkeypatch.setattr(recipe, "OPFPath", lambda: OPFPath("unexpected.opf"))
    elif phase == "output_validation":
        original_info = EPUB.info

        def fail_output_info(epub):
            if epub.path != book_path:
                raise ValueError("Output invalid")
            return original_info(epub)

        monkeypatch.setattr(EPUB, "info", fail_output_info)
    run = recipe._fully_process_encrypted_panda_with_context(str(book_path))
    assert not run.success and run.skip is None
    assert run.new_epub is None
    assert run.error == EpubErrorReason.UNKNOWN
    assert "Source cleanup failed" in run.details
    if phase == "output_validation":
        assert "Output invalid" in run.details
    assert len(run.analytics) == (0 if phase == "skip" else 1)
    assert not (recipe.settings.decrypted_epub_dir / book_path.name).exists()


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
