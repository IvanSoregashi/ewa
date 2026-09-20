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


@pytest.mark.parametrize("dry_run", [False, True])
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
def test_legacy_and_context_results_and_exported_contents_match(recipe, tmp_path, monkeypatch, scenario, dry_run):
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
        run = process(str(path), dry_run=dry_run)
        results.append(run)
        exported_contents.append(exports.copy())
        destination = recipe.settings.decrypted_epub_dir / path.name
        processed = recipe.settings.processed_epub_dir / path.name
        if run.success and not dry_run:
            assert destination.exists()
            assert not path.exists()
            assert processed.read_bytes() == original
            # Restore only this temporary fixture so the second recipe gets the same input.
            processed.rename(path)
            destination.unlink()
        else:
            assert (path.read_bytes() if path.exists() else None) == original
            assert not destination.exists()
            assert not processed.exists()

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


@pytest.mark.parametrize("referenced", [False, True])
def test_both_recipes_leave_undeclared_image_out_of_manifest(recipe, monkeypatch, referenced):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub", referenced=referenced)
    destination = recipe.settings.decrypted_epub_dir / path.name
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

    original = path.read_bytes()
    exports = []
    original_export = EPUB.package_into

    def capture_export(epub, destination, **kwargs):
        original_export(epub, destination, **kwargs)
        output = EPUB(destination)
        assert [resource.filename for resource in output.package.undeclared_resources] == ["cover.jpg"]
        assert output.package.manifest_item_by_path("cover.jpg") is None
        assert output.package.manifest_item_by_path("cover.png") is None
        with ZipFile(destination) as archive:
            exports.append([(name, archive.read(name)) for name in archive.namelist()])

    monkeypatch.setattr(EPUB, "package_into", capture_export)
    legacy = recipe._fully_process_encrypted_panda(str(path), dry_run=True)
    assert not destination.exists()
    candidate = recipe._fully_process_encrypted_panda_with_context(str(path), dry_run=True)
    assert run_data(legacy) == run_data(candidate)
    if referenced:
        assert candidate.success and candidate.skip is None
        assert len(exports) == 2
        assert exports[0] == exports[1]
    else:
        assert legacy.skip == EpubSkipReason.UNMATCHED_LINKS and legacy.error is None
        assert exports == []
    assert candidate.error is None
    assert run_data(legacy)[1] == run_data(candidate)[1]
    assert path.read_bytes() == original
    assert not destination.exists()


@pytest.mark.parametrize("phase", ["success", "skip", "translation", "export", "output_validation"])
def test_cleanup_failure_exposes_diagnostic_difference(recipe, monkeypatch, phase):
    path = write_book(recipe.settings.encrypted_epub_dir / "book.epub", referenced=phase != "skip")
    original = path.read_bytes()
    destination = recipe.settings.decrypted_epub_dir / path.name
    original_open = EPUB.keep_open
    depth = 0

    @contextmanager
    def fail_cleanup(epub):
        nonlocal depth
        depth += 1
        try:
            with original_open(epub) as opened:
                yield opened
        finally:
            depth -= 1
            if depth == 0 and epub.path == path:
                raise OSError("Source cleanup failed")

    monkeypatch.setattr(EPUB, "keep_open", fail_cleanup)
    if phase == "translation":

        def fail_translation(*args):
            raise ValueError("Translation failed")

        monkeypatch.setattr(recipe.html_editing, "translate_text", fail_translation)
        monkeypatch.setattr(recipe.recipe_htmls, "translate_text", fail_translation)
    elif phase == "export":

        def fail_export(epub, destination, **kwargs):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"partial output")
            raise OSError("Export failed")

        monkeypatch.setattr(EPUB, "package_into", fail_export)
    elif phase == "output_validation":
        original_info = EPUB.info

        def fail_validation(epub):
            if epub.path == destination:
                raise ValueError("Output invalid")
            return original_info(epub)

        monkeypatch.setattr(EPUB, "info", fail_validation)

    legacy = recipe._fully_process_encrypted_panda(str(path))
    assert not destination.exists()
    candidate = recipe._fully_process_encrypted_panda_with_context(str(path))
    assert legacy.error == candidate.error == EpubErrorReason.UNKNOWN
    assert legacy.skip is None and candidate.skip is None
    assert not legacy.success and not candidate.success
    assert legacy.details == "OSError('Source cleanup failed')"
    assert candidate.details.endswith("Closing EPUB: OSError('Source cleanup failed')")
    if phase != "success":
        assert {
            "skip": "cover.png",
            "translation": "Translation failed",
            "export": "Export failed",
            "output_validation": "Output invalid",
        }[phase] in candidate.details
    legacy_data, legacy_analytics = run_data(legacy)
    candidate_data, candidate_analytics = run_data(candidate)
    legacy_data.pop("details")
    candidate_data.pop("details")
    assert legacy_data == candidate_data
    assert legacy_analytics == candidate_analytics
    assert len(candidate_analytics) == 1
    assert path.read_bytes() == original
    assert not destination.exists()
