import json
import random
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

import pytest
from PIL import Image
from lxml import etree

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.image_analytics import ImageOptimizationRecord
from epub.processing import ProcessingContext
from epub.recipe_htmls import ReplaceLinks
from epub.recipe_image import OptimizeImages
from epub.verification import NoUnmatchedLinks
from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import MediaType
from library.image.models import ImageErrorReason, ImageSkipReason


@pytest.fixture
def image_bytes():
    buffer = BytesIO()
    with Image.frombytes("RGB", (256, 256), random.Random(0).randbytes(256 * 256 * 3)) as image:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_book(tmp_path, images, *, referenced=None, declared=None):
    referenced = list(images) if referenced is None else referenced
    declared = list(images) if declared is None else declared
    declarations = "".join(
        f'<item id="image{i}" href="images/{name}" media-type="image/{PurePosixPath(name).suffix[1:].lower()}"/>'
        for i, name in enumerate(declared)
    )
    links = "".join(f'<img src="../images/{name}"/>' for name in referenced)
    path = tmp_path / "book.epub"
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "OEBPS/content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Images</dc:title></metadata>'
            '<manifest><item id="chapter" href="text/chapter.xhtml" media-type="application/xhtml+xml"/>'
            f'{declarations}</manifest><spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr("OEBPS/text/chapter.xhtml", f"<html><body>{links}</body></html>")
        for name, content in images.items():
            archive.writestr(f"OEBPS/images/{name}", content)
    return path


def export(context, tmp_path):
    destination = tmp_path / "processed.epub"
    context.epub.package_into(destination)
    output = EPUB(destination)
    context.succeed(output.info())
    return output


def test_conversion_updates_inventory_html_manifest_and_export(tmp_path, image_bytes):
    path = make_book(tmp_path, {"cover.png": image_bytes})
    original = path.read_bytes()
    with ProcessingContext() as context:
        context.open_epub(path).perform(OptimizeImages())
        assert context.replacements == {"OEBPS/images/cover.png": "OEBPS/images/cover.jpg"}
        assert context.epub.resources.by_path("OEBPS/images/cover.png") is None
        # Both consumers still need the original path at this point.
        assert context.epub.package.manifest_item_by_path("OEBPS/images/cover.png") is not None
        context.perform(ReplaceLinks()).verify(NoUnmatchedLinks())
        assert context.replacements == {}
        output = export(context, tmp_path)

    run = require(context.result)
    assert run.success, run.details
    assert len(run.analytics) == 1
    record = run.analytics[0]
    assert isinstance(record, ImageOptimizationRecord)
    assert record.success and record.run_id == run.id
    assert record.original_image.path == "OEBPS/images/cover.png"
    assert require(record.new_image).path == "OEBPS/images/cover.jpg"
    assert output.resources.by_path("OEBPS/images/cover.png") is None
    resource = require(output.resources.by_path("OEBPS/images/cover.jpg"))
    assert resource.media_type == MediaType.IMAGE_JPEG
    with Image.open(BytesIO(resource.content)) as image:
        assert image.format == "JPEG"
        assert image.size == require(record.new_image).size
    assert len(resource.content) == require(record.new_image).filesize
    chapter = require(output.resources.by_path("OEBPS/text/chapter.xhtml"))
    assert etree.fromstring(chapter.content).xpath("//img/@src") == ["../images/cover.jpg"]
    item = require(output.package.manifest_item_by_path(resource.filename))
    assert item.href == "images/cover.jpg"
    assert item.media_type == "image/jpeg"
    assert output.package.resource_for_href(item.href) is resource
    assert path.read_bytes() == original


def test_small_and_broken_images_stay_unchanged_and_svg_is_excluded(tmp_path):
    buffer = BytesIO()
    with Image.new("RGB", (8, 8)) as image:
        image.save(buffer, format="PNG")
    images = {"small.png": buffer.getvalue(), "broken.png": b"invalid", "vector.svg": b"<svg/>"}
    path = make_book(tmp_path, images)
    with ProcessingContext() as context:
        context.open_epub(path)
        chapter = require(context.epub.resources.by_path("OEBPS/text/chapter.xhtml"))
        before = chapter.content
        context.perform(OptimizeImages()).perform(ReplaceLinks())
        assert context.replacements == {}
        assert chapter.content == before  # Empty mapping avoids parsing/serializing HTML.
        output = export(context, tmp_path)

    run = require(context.result)
    assert run.success, run.details
    small, broken = run.analytics
    assert isinstance(small, ImageOptimizationRecord) and isinstance(broken, ImageOptimizationRecord)
    assert small.skip == ImageSkipReason.SMALL_IMAGE
    assert broken.error == ImageErrorReason.DECODE_FAILED
    assert small.run_id == broken.run_id == run.id
    for name, content in images.items():
        assert require(output.resources.by_path(f"OEBPS/images/{name}")).content == content


def test_success_without_rename_does_not_require_html_match(tmp_path, image_bytes):
    buffer = BytesIO()
    with Image.open(BytesIO(image_bytes)) as image:
        image.save(buffer, format="JPEG", quality=100)
    path = make_book(tmp_path, {"cover.jpg": buffer.getvalue()}, referenced=[])
    with ProcessingContext() as context:
        context.open_epub(path).perform(OptimizeImages()).perform(ReplaceLinks())
        assert context.replacements == {}
        output = export(context, tmp_path)

    run = require(context.result)
    assert run.success, run.details
    record = run.analytics[0]
    assert isinstance(record, ImageOptimizationRecord) and record.success
    assert require(output.resources.by_path("OEBPS/images/cover.jpg")).content != buffer.getvalue()


@pytest.mark.parametrize("collision", ["cover.jpg", "cover.PNG"])
def test_collision_stops_book_without_overwrite_and_retains_earlier_evidence(tmp_path, image_bytes, collision):
    images = {"first.png": image_bytes, "cover.png": image_bytes, collision: image_bytes}
    path = make_book(tmp_path, images)
    original = path.read_bytes()
    with ProcessingContext() as context:
        context.open_epub(path).perform(OptimizeImages())
        pytest.fail("Rename collision must stop processing")

    run = require(context.result)
    assert run.error == EpubErrorReason.UNKNOWN
    assert "Resource already exists" in run.details
    expected_count = 1 if collision == "cover.jpg" else 2
    assert len(run.analytics) == expected_count
    assert all(isinstance(record, ImageOptimizationRecord) and record.success for record in run.analytics)
    failed_name = "cover.png" if collision == "cover.jpg" else "cover.PNG"
    assert require(context.epub.resources.by_path(f"OEBPS/images/{failed_name}")).content == image_bytes
    target = require(context.epub.resources.by_path("OEBPS/images/cover.jpg"))
    if collision == "cover.jpg":
        assert target.content == image_bytes
    else:
        with Image.open(BytesIO(target.content)) as image:
            assert image.format == "JPEG"
    assert "OEBPS/images/first.png" in context.replacements
    assert f"OEBPS/images/{failed_name}" not in context.replacements
    assert path.read_bytes() == original


@pytest.mark.parametrize("verify_links", [False, True])
def test_unmatched_rename_only_skips_when_recipe_verifies_links(tmp_path, image_bytes, verify_links):
    path = make_book(tmp_path, {"cover.png": image_bytes, "orphan.png": image_bytes}, referenced=["cover.png"])
    with ProcessingContext() as context:
        context.open_epub(path).perform(OptimizeImages()).perform(ReplaceLinks())
        assert context.replacements == {}
        assert context.unmatched_links == {"OEBPS/images/orphan.png": "OEBPS/images/orphan.jpg"}
        assert context.epub.package.manifest_item_by_path("OEBPS/images/orphan.jpg") is not None
        # An empty replacement pass must not erase evidence before verification.
        context.perform(ReplaceLinks())
        if verify_links:
            context.verify(NoUnmatchedLinks())
            pytest.fail("Failed verification must stop processing")
        export(context, tmp_path)

    run = require(context.result)
    assert run.success == (not verify_links)
    assert run.skip == (EpubSkipReason.UNMATCHED_LINKS if verify_links else None)
    assert run.error is None
    if verify_links:
        assert json.loads(run.details) == context.unmatched_links
    assert len(run.analytics) == 2
    assert context.replacements == {}
    assert context.epub.package.manifest_item_by_path("OEBPS/images/cover.jpg") is not None
    assert b"cover.jpg" in require(context.epub.resources.by_path("OEBPS/text/chapter.xhtml")).content
    assert (tmp_path / "processed.epub").exists() == (not verify_links)


def test_manifest_failure_keeps_mapping_after_html_consumed_it(tmp_path, image_bytes):
    path = make_book(tmp_path, {"cover.png": image_bytes}, declared=[])
    with ProcessingContext() as context:
        context.open_epub(path).perform(OptimizeImages()).perform(ReplaceLinks())
        pytest.fail("Missing manifest entry must stop processing")

    run = require(context.result)
    assert run.error == EpubErrorReason.UNKNOWN
    assert "Manifest(OEBPS/images/cover.png)" in run.details
    assert len(run.analytics) == 1
    assert context.replacements == {"OEBPS/images/cover.png": "OEBPS/images/cover.jpg"}
    assert b"cover.jpg" in require(context.epub.resources.by_path("OEBPS/text/chapter.xhtml")).content
