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
from library.epub.metadata import MetadataType
from library.image.models import ImageErrorReason, ImageSkipReason


@pytest.fixture
def optimize_images():
    return OptimizeImages


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


def test_conversion_updates_inventory_html_manifest_and_export(tmp_path, image_bytes, optimize_images):
    path = make_book(tmp_path, {"cover.png": image_bytes})
    original = path.read_bytes()
    with ProcessingContext() as context:
        context.open_epub(path).perform(optimize_images())
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


def test_conversion_preserves_resource_identity_and_manifest_dependents(tmp_path, image_bytes, optimize_images):
    path = make_book(tmp_path, {"cover.png": image_bytes})
    with ProcessingContext() as context:
        context.open_epub(path)
        package = context.epub.package
        resource = context.epub.resources.by_path("OEBPS/images/cover.png")
        item = package.manifest_item_by_path(resource.filename)
        item.properties = "cover-image"
        chapter = package.document.manifest.find_item(id="chapter")
        chapter.fallback = item.id
        metadata = package.document.metadata
        metadata.add_metadata(MetadataType.META, "", dc=False, name="cover", content=item.id)
        context.perform(optimize_images()).perform(ReplaceLinks())
        assert context.epub.resources.by_path("OEBPS/images/cover.jpg") is resource
        assert package.manifest_item_by_path(resource.filename) is item
        assert item.id == "image0" and item.properties == "cover-image"
        assert chapter.fallback == item.id
        assert package.document.metadata.referencing({item.id})
        output = export(context, tmp_path)
    assert context.result.success, context.result.details
    saved_item = output.package.manifest_item_by_path("OEBPS/images/cover.jpg")
    assert saved_item.id == "image0" and saved_item.properties == "cover-image"
    assert output.package.document.manifest.find_item(id="chapter").fallback == "image0"
    assert output.package.document.metadata.referencing({"image0"})


@pytest.mark.parametrize("referenced", [False, True])
def test_png_optimization_without_conversion_needs_no_link_operation(
    tmp_path, image_bytes, referenced, optimize_images
):
    path = make_book(tmp_path, {"cover.png": image_bytes}, referenced=["cover.png"] if referenced else [])
    with ProcessingContext() as context:
        context.open_epub(path)
        chapter = require(context.epub.resources.by_path("OEBPS/text/chapter.xhtml")).content
        context.perform(optimize_images(convert_png_to_jpeg=False, min_filesize=0, max_dimensions=(128, 128)))
        assert context.replacements == {}
        assert NoUnmatchedLinks().verify(context) is None
        # Export directly: no HTML or manifest link-replacement step is needed.
        output = export(context, tmp_path)

    run = require(context.result)
    assert run.success and len(run.analytics) == 1
    record = run.analytics[0]
    assert isinstance(record, ImageOptimizationRecord)
    assert record.success and record.run_id == run.id
    resource = require(output.resources.by_path("OEBPS/images/cover.png"))
    assert resource.content != image_bytes and len(resource.content) == require(record.new_image).filesize
    assert output.resources.by_path("OEBPS/images/cover.jpg") is None
    with Image.open(BytesIO(resource.content)) as image:
        assert image.format == "PNG" and image.size == (128, 128)
    assert require(output.resources.by_path("OEBPS/text/chapter.xhtml")).content == chapter
    item = require(output.package.manifest_item_by_path("OEBPS/images/cover.png"))
    assert item.href == "images/cover.png" and item.media_type == "image/png"


def test_small_and_broken_images_stay_unchanged_and_svg_is_excluded(tmp_path, optimize_images):
    buffer = BytesIO()
    with Image.new("RGB", (8, 8)) as image:
        image.save(buffer, format="PNG")
    images = {"small.png": buffer.getvalue(), "broken.png": b"invalid", "vector.svg": b"<svg/>"}
    path = make_book(tmp_path, images)
    with ProcessingContext() as context:
        context.open_epub(path)
        chapter = require(context.epub.resources.by_path("OEBPS/text/chapter.xhtml"))
        before = chapter.content
        context.perform(optimize_images()).perform(ReplaceLinks())
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


def test_success_without_rename_does_not_require_html_match(tmp_path, image_bytes, optimize_images):
    buffer = BytesIO()
    with Image.open(BytesIO(image_bytes)) as image:
        image.save(buffer, format="JPEG", quality=100)
    path = make_book(tmp_path, {"cover.jpg": buffer.getvalue()}, referenced=[])
    with ProcessingContext() as context:
        context.open_epub(path).perform(optimize_images()).perform(ReplaceLinks())
        assert context.replacements == {}
        output = export(context, tmp_path)

    run = require(context.result)
    assert run.success, run.details
    record = run.analytics[0]
    assert isinstance(record, ImageOptimizationRecord) and record.success
    assert require(output.resources.by_path("OEBPS/images/cover.jpg")).content != buffer.getvalue()


@pytest.mark.parametrize(
    "occupied,expected",
    [
        ([], "cover.jpg"),
        (["cover.jpg"], "cover_1.jpg"),
        (["cover.jpg", "cover_1.jpg"], "cover_2.jpg"),
        (["cover.jpg", "cover_2.jpg"], "cover_1.jpg"),
        (["cover.jpg", "cover_1.jpg", "cover_2.jpg"], "cover_3.jpg"),
    ],
)
def test_conversion_chooses_free_name_and_preserves_existing_resources(
    tmp_path, image_bytes, occupied, expected, optimize_images
):
    buffer = BytesIO()
    with Image.new("RGB", (8, 8)) as image:
        image.save(buffer, format="JPEG")
    existing = buffer.getvalue()
    images = {"first.png": image_bytes, "cover.png": image_bytes, **dict.fromkeys(occupied, existing)}
    path = make_book(tmp_path, images)
    original = path.read_bytes()
    destination = f"OEBPS/images/{expected}"
    with ProcessingContext() as context:
        context.open_epub(path).perform(optimize_images())
        assert context.replacements == {
            "OEBPS/images/first.png": "OEBPS/images/first.jpg",
            "OEBPS/images/cover.png": destination,
        }
        context.perform(ReplaceLinks()).verify(NoUnmatchedLinks())
        output = export(context, tmp_path)
    run = require(context.result)
    assert run.success, run.details
    assert len(run.analytics) == len(images)
    converted = next(record for record in run.analytics if record.original_image.path.endswith("/cover.png"))
    assert converted.success and require(converted.new_image).path == destination
    with Image.open(BytesIO(require(output.resources.by_path(destination)).content)) as image:
        image.load()
        assert image.format == "JPEG"
    for name in occupied:
        resource = require(output.resources.by_path(f"OEBPS/images/{name}"))
        assert resource.content == existing
        assert require(output.package.manifest_item_by_path(resource.filename)).href == f"images/{name}"
    item = require(output.package.manifest_item_by_path(destination))
    assert item.id == "image1" and item.media_type == "image/jpeg" and item.href == f"images/{expected}"
    chapter = require(output.resources.by_path("OEBPS/text/chapter.xhtml"))
    assert etree.fromstring(chapter.content).xpath("//img/@src") == [
        "../images/first.jpg",
        f"../images/{expected}",
        *[f"../images/{name}" for name in occupied],
    ]
    assert path.read_bytes() == original


def test_two_pngs_with_same_stem_get_distinct_jpeg_paths(tmp_path, image_bytes, optimize_images):
    path = make_book(tmp_path, {"cover.png": image_bytes, "cover.PNG": image_bytes})
    with ProcessingContext() as context:
        context.open_epub(path).perform(optimize_images())
        assert context.replacements == {
            "OEBPS/images/cover.png": "OEBPS/images/cover.jpg",
            "OEBPS/images/cover.PNG": "OEBPS/images/cover_1.jpg",
        }
        context.perform(ReplaceLinks()).verify(NoUnmatchedLinks())
        output = export(context, tmp_path)
    assert context.result.success, context.result.details
    assert all(record.success for record in context.result.analytics)
    for name in ("cover.jpg", "cover_1.jpg"):
        assert output.resources.by_path(f"OEBPS/images/{name}") is not None
        assert output.package.manifest_item_by_path(f"OEBPS/images/{name}") is not None
    chapter = require(output.resources.by_path("OEBPS/text/chapter.xhtml"))
    assert etree.fromstring(chapter.content).xpath("//img/@src") == ["../images/cover.jpg", "../images/cover_1.jpg"]


@pytest.mark.parametrize("verify_links", [False, True])
def test_unmatched_rename_only_skips_when_recipe_verifies_links(tmp_path, image_bytes, verify_links, optimize_images):
    path = make_book(tmp_path, {"cover.png": image_bytes, "orphan.png": image_bytes}, referenced=["cover.png"])
    with ProcessingContext() as context:
        context.open_epub(path).perform(optimize_images()).perform(ReplaceLinks())
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


@pytest.mark.parametrize("referenced", [False, True])
@pytest.mark.parametrize("declared", [False, True])
def test_missing_links_are_reported_independently_without_adding_declarations(
    tmp_path, image_bytes, referenced, declared, optimize_images
):
    path = make_book(
        tmp_path,
        {"orphan.png": image_bytes, "cover.png": image_bytes},
        referenced=["cover.png", *(["orphan.png"] if referenced else [])],
        declared=["cover.png", *(["orphan.png"] if declared else [])],
    )
    missing = {"OEBPS/images/orphan.png": "OEBPS/images/orphan.jpg"}
    original = path.read_bytes()
    with ProcessingContext() as context:
        context.open_epub(path).perform(optimize_images()).perform(ReplaceLinks())
        assert context.unmatched_links == ({} if referenced else missing)
        assert context.unmatched_manifest_links == ({} if declared else missing)
        assert context.replacements == {}
        assert len(context.epub.package.document.manifest.items) == (3 if declared else 2)
        # Missing the first declaration must not prevent replacing a later one.
        assert context.epub.package.manifest_item_by_path("OEBPS/images/cover.jpg") is not None
        assert (context.epub.package.manifest_item_by_path("OEBPS/images/orphan.jpg") is not None) == declared
        context.perform(ReplaceLinks())
        assert context.unmatched_links == ({} if referenced else missing)
        assert context.unmatched_manifest_links == ({} if declared else missing)
        assert (NoUnmatchedLinks().verify(context) is None) == referenced
        output = export(context, tmp_path)

    run = require(context.result)
    assert run.success and run.error is None
    assert len(run.analytics) == 2
    assert (output.package.manifest_item_by_path("OEBPS/images/orphan.jpg") is not None) == declared
    chapter = require(output.resources.by_path("OEBPS/text/chapter.xhtml")).content
    assert b"cover.jpg" in chapter
    assert (b"orphan.jpg" in chapter) == referenced
    assert path.read_bytes() == original


def test_nonempty_replacement_pass_refreshes_both_missing_link_reports(tmp_path, image_bytes, optimize_images):
    path = make_book(tmp_path, {"cover.png": image_bytes})
    with ProcessingContext() as context:
        context.open_epub(path)
        context.unmatched_links = {"old.png": "old.jpg"}
        context.unmatched_manifest_links = {"old.png": "old.jpg"}
        context.perform(optimize_images()).perform(ReplaceLinks())
        assert context.unmatched_links == {}
        assert context.unmatched_manifest_links == {}
        export(context, tmp_path)
    assert require(context.result).success


def test_missing_replacement_resource_keeps_mapping_after_html_consumed_it(tmp_path, image_bytes, optimize_images):
    path = make_book(tmp_path, {"cover.png": image_bytes})
    with ProcessingContext() as context:
        context.open_epub(path).perform(optimize_images())
        context.epub.resources.remove(require(context.epub.resources.by_path("OEBPS/images/cover.jpg")))
        context.perform(ReplaceLinks())
        pytest.fail("An existing declaration cannot point to a missing replacement resource")

    run = require(context.result)
    assert run.error == EpubErrorReason.UNKNOWN
    assert "Resource(OEBPS/images/cover.jpg)" in run.details
    assert len(run.analytics) == 1
    assert context.replacements == {"OEBPS/images/cover.png": "OEBPS/images/cover.jpg"}
    assert b"cover.jpg" in require(context.epub.resources.by_path("OEBPS/text/chapter.xhtml")).content
