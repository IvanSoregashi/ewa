from contextlib import contextmanager
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image

from epub.errors import EpubErrorReason, EpubSkipReason
from library.epub.epub import EPUB
from test_recipe_run import recipe as recipe, write_book


def run_data(run):
    # UUIDs identify distinct attempts; compare their data and verify each link separately.
    assert all(record.run_id == run.id for record in run.analytics)
    return (
        run.model_dump(mode="json", exclude={"id"}),
        [record.model_dump(mode="json", exclude={"id", "run_id"}) for record in run.analytics],
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "conversion",
        "multiple_fonts",
        "small_image",
        "broken_image",
        "unmatched_links",
        "wrong_opf",
        "no_font",
        "missing_source",
        "bad_archive",
        "bad_metadata",
        "translation_failure",
        "export_failure",
        "output_validation_failure",
        "collision",
    ],
)
def test_legacy_and_context_results_and_exported_contents_match(recipe, tmp_path, monkeypatch, scenario):
    path = recipe.settings.encrypted_epub_dir / "book.epub"
    if scenario == "multiple_fonts":
        write_book(path, fonts=("fonts/SerenePanda.ttf", "other/SerenePanda.ttf"))
    elif scenario == "wrong_opf":
        write_book(path, opf_path="OEBPS/content.opf")
    elif scenario == "no_font":
        write_book(path, fonts=())
    elif scenario == "missing_source":
        pass
    elif scenario == "bad_archive":
        path.write_bytes(b"invalid archive")
    elif scenario == "bad_metadata":
        with ZipFile(path, "w") as archive:
            archive.writestr("content.opf", "<broken")
    else:
        write_book(path, referenced=scenario != "unmatched_links")

    if scenario in {"small_image", "broken_image"}:
        with ZipFile(path) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        if scenario == "small_image":
            buffer = BytesIO()
            with Image.new("RGB", (8, 8)) as image:
                image.save(buffer, format="PNG")
            files["cover.png"] = buffer.getvalue()
        else:
            files["cover.png"] = b"not an image"
        with ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
    elif scenario == "collision":
        with ZipFile(path, "a") as archive:
            archive.writestr("cover.jpg", b"existing resource")

    monkeypatch.setattr(recipe, "sp_dictionary", str.maketrans({"T": "D"}))
    if scenario == "translation_failure":

        def fail_translation(*args):
            raise ValueError("Translation failed")

        monkeypatch.setattr(recipe.html_editing, "translate_text", fail_translation)
        monkeypatch.setattr(recipe.recipe_htmls, "translate_text", fail_translation)
    elif scenario == "output_validation_failure":
        original_info = EPUB.info

        def fail_validation(epub):
            if epub.path.parent == recipe.settings.decrypted_epub_dir:
                raise ValueError("Output invalid")
            return original_info(epub)

        monkeypatch.setattr(EPUB, "info", fail_validation)

    exports = []
    original_export = EPUB.package_into

    def capture_export(epub, destination, **kwargs):
        if scenario == "export_failure":
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"partial output")
            raise OSError("Export failed")
        original_export(epub, destination, **kwargs)
        with ZipFile(destination) as archive:
            exports.append([(name, archive.read(name)) for name in archive.namelist()])

    monkeypatch.setattr(EPUB, "package_into", capture_export)

    original = path.read_bytes() if path.exists() else None
    results = []
    exported_contents = []
    for process in (recipe._fully_process_encrypted_panda, recipe._fully_process_encrypted_panda_with_context):
        exports.clear()
        run = process(str(path))
        results.append(run)
        exported_contents.append(exports.copy())
        assert (path.read_bytes() if path.exists() else None) == original
        assert not (recipe.settings.decrypted_epub_dir / path.name).exists()
        assert not (recipe.settings.processed_epub_dir / path.name).exists()

    assert results[0].id != results[1].id
    assert run_data(results[0]) == run_data(results[1])
    assert exported_contents[0] == exported_contents[1]
    success = scenario in {"conversion", "multiple_fonts", "small_image", "broken_image"}
    assert results[0].success == success
    if success:
        assert len(exported_contents[0]) == 1
    if scenario in {"conversion", "multiple_fonts"}:
        chapter = dict(exported_contents[0][0])["chapter.xhtml"]
        assert b"Dext" in chapter and b"cover.jpg" in chapter


def test_undeclared_orphan_exposes_reference_order_difference(recipe):
    """Keep this discrepancy visible until the candidate's skip/error ordering is decided."""
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub", referenced=False)
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    from lxml import etree

    package = etree.fromstring(files["content.opf"])
    item = package.xpath('//*[local-name()="item"][@href="cover.png"]')[0]
    item.getparent().remove(item)
    files["content.opf"] = etree.tostring(package)
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    legacy = recipe._fully_process_encrypted_panda(str(path))
    candidate = recipe._fully_process_encrypted_panda_with_context(str(path))
    assert legacy.skip == EpubSkipReason.UNMATCHED_LINKS and legacy.error is None
    assert candidate.skip is None and candidate.error == EpubErrorReason.UNKNOWN
    assert "Manifest(cover.png)" in candidate.details
    assert run_data(legacy)[1] == run_data(candidate)[1]


def test_cleanup_failure_exposes_diagnostic_difference(recipe, monkeypatch):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub")
    original_open = EPUB.keep_open
    depth = 0

    @contextmanager
    def fail_cleanup(epub):
        nonlocal depth
        depth += 1
        try:
            with original_open(epub) as opened:
                yield opened
            if depth == 1 and epub.path == path:
                raise OSError("Source cleanup failed")
        finally:
            depth -= 1

    monkeypatch.setattr(EPUB, "keep_open", fail_cleanup)
    legacy = recipe._fully_process_encrypted_panda(str(path))
    candidate = recipe._fully_process_encrypted_panda_with_context(str(path))
    assert legacy.error == candidate.error == EpubErrorReason.UNKNOWN
    assert legacy.details == "OSError('Source cleanup failed')"
    assert candidate.details == "Closing EPUB: OSError('Source cleanup failed')"
    legacy_data, legacy_analytics = run_data(legacy)
    candidate_data, candidate_analytics = run_data(candidate)
    legacy_data.pop("details")
    candidate_data.pop("details")
    assert legacy_data == candidate_data
    assert legacy_analytics == candidate_analytics
