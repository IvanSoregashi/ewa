from io import BytesIO
import json
import random
import shutil
import subprocess
from zipfile import ZipFile

import pytest
from PIL import Image
from lxml import etree

from epub import recipe_gif
from library.epub.epub import EPUB
from library.epub.resources import Resource
from library.image.constants import ANIMATION_CRF
from library.image.models import ImageSkipReason
from library.image.recipe import optimize_image


def gif_bytes(*, animated=True, padded=True):
    with BytesIO() as buffer, Image.new("RGB", (32, 24), "red") as first, Image.new("RGB", (32, 24), "blue") as second:
        first.save(buffer, "GIF", save_all=animated, append_images=[second] if animated else [], duration=100, loop=0)
        content = buffer.getvalue()
    return content.ljust(10_000, b"\0") if padded else content


def make_book(tmp_path, content, *, declared=True):
    path = tmp_path / "animation.epub"
    declaration = '<item id="animation" href="images/clip.gif" media-type="image/gif"/>' if declared else ""
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Animation test</dc:title></metadata>'
            f'<manifest>{declaration}<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr("chapter.xhtml", '<html><body><img src="images/clip.gif"/></body></html>')
        archive.writestr("images/clip.gif", content)
    return EPUB(path)


def test_dedicated_conversion_updates_video_poster_manifest_and_chapter(tmp_path, monkeypatch):
    content = gif_bytes()
    book = make_book(tmp_path, content)
    resource = book.resources.by_path("images/clip.gif")
    calls = []

    def encode(image, original_size, **options):
        calls.append((image.size, original_size, options))
        return b"video", {}

    monkeypatch.setattr(recipe_gif, "convert_to_mp4", encode)
    regular, _ = optimize_image(content, min_filesize=0)
    assert regular.skip == ImageSkipReason.HAS_ANIMATION
    table = recipe_gif.convert_giant_gifs(book, size_limit=0)
    assert calls == [((32, 24), len(content), {"crf": ANIMATION_CRF, "source_bytes": content})]
    assert book.resources.by_path("images/clip.gif") is None
    assert book.resources.by_path("images/clip.mp4") is resource
    assert resource.content == b"video"
    item = book.package.manifest_item_by_path("images/clip.mp4")
    assert item.id == "animation" and item.media_type == "video/mp4"
    poster = book.resources.by_path("images/clip.jpg")
    with Image.open(BytesIO(poster.content)) as image:
        assert image.format == "JPEG" and image.size == (32, 24)
    assert recipe_gif.rewrite_gif_chapters(book, table) == 1
    chapter = etree.fromstring(book.resources.by_path("chapter.xhtml").content)
    assert chapter.xpath("//video/@src") == ["images/clip.mp4"]
    assert chapter.xpath("//video/@poster") == ["images/clip.jpg"]
    output = tmp_path / "output.epub"
    book.package_into(output)
    reopened = EPUB(output)
    assert reopened.resources.by_path("images/clip.gif") is None
    assert reopened.package.manifest_item_by_path("images/clip.jpg").media_type == "image/jpeg"


@pytest.mark.parametrize(
    "case", ["static", "small", "undeclared", "invalid", "missing_encoder", "encoder_error", "poster_error", "larger"]
)
def test_failed_or_ineligible_conversion_keeps_gif(tmp_path, monkeypatch, case):
    content = b"broken GIF" if case == "invalid" else gif_bytes(animated=case != "static")
    book = make_book(tmp_path, content, declared=case != "undeclared")
    resource = book.resources.by_path("images/clip.gif")
    manifest = book.package.document.to_xml_bytes()

    def encode(*args, **kwargs):
        if case in ("static", "small", "undeclared", "invalid"):
            pytest.fail("Ineligible inputs must not reach the encoder")
        if case == "encoder_error":
            raise OSError("encoder failed")
        if case == "missing_encoder":
            return None, {"skipped": "ffmpeg not found"}
        return (content if case == "larger" else b"video"), {}

    def fail_poster(*args, **kwargs):
        raise OSError("poster failed")

    monkeypatch.setattr(recipe_gif, "convert_to_mp4", encode)
    if case == "poster_error":
        monkeypatch.setattr(recipe_gif, "generate_poster", fail_poster)
    assert recipe_gif.convert_giant_gifs(book, size_limit=len(content) if case == "small" else 0) == {}
    assert resource.filename == "images/clip.gif" and resource.content == content
    assert book.resources.by_path("images/clip.mp4") is None
    assert book.resources.by_path("images/clip.jpg") is None
    assert book.package.document.to_xml_bytes() == manifest


@pytest.mark.parametrize("combined_size", [9499, 9500, 9501])
def test_savings_gate_includes_poster_and_requires_more_than_five_percent(tmp_path, monkeypatch, combined_size):
    content = gif_bytes()
    book = make_book(tmp_path, content)
    monkeypatch.setattr(recipe_gif, "generate_poster", lambda content: (b"poster", (32, 24)))
    monkeypatch.setattr(recipe_gif, "convert_to_mp4", lambda *args, **kwargs: (bytes(combined_size - 6), {}))
    table = recipe_gif.convert_giant_gifs(book, size_limit=0)
    assert bool(table) == (combined_size < 9500)
    if not table:
        assert book.resources.by_path("images/clip.gif").content == content
        assert book.resources.by_path("images/clip.jpg") is None


@pytest.mark.parametrize("collision", ["video", "video_directory", "poster", "poster_id", "declared_video"])
def test_collision_does_not_mutate_gif(tmp_path, monkeypatch, collision):
    content = gif_bytes()
    book = make_book(tmp_path, content)
    if collision == "video_directory":
        book.resources.add(Resource.from_bytes("images/clip.mp4/child", b"existing"))
    elif collision in ("video", "poster"):
        book.resources.add(
            Resource.from_bytes("images/clip." + ("mp4" if collision == "video" else "jpg"), b"existing")
        )
    else:
        book.package.document.manifest.add_item(
            id="animation-poster" if collision == "poster_id" else "another-video",
            href="another.jpg" if collision == "poster_id" else "images/clip.mp4",
            media_type="image/jpeg" if collision == "poster_id" else "video/mp4",
        )
    manifest = book.package.document.to_xml_bytes()
    original_paths = [resource.filename for resource in book.resources]
    monkeypatch.setattr(recipe_gif, "convert_to_mp4", lambda *args, **kwargs: (b"video", {}))
    with pytest.raises(ValueError):
        recipe_gif.convert_giant_gifs(book, size_limit=0)
    assert book.resources.by_path("images/clip.gif").content == content
    assert [resource.filename for resource in book.resources] == original_paths
    assert book.package.document.to_xml_bytes() == manifest


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg/ffprobe unavailable")
def test_real_ffmpeg_conversion(tmp_path):
    frames = [Image.frombytes("RGB", (128, 96), random.Random(seed).randbytes(128 * 96 * 3)) for seed in range(12)]
    try:
        with BytesIO() as buffer:
            frames[0].save(buffer, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
            content = buffer.getvalue()
    finally:
        for frame in frames:
            frame.close()
    book = make_book(tmp_path, content)
    table = recipe_gif.convert_giant_gifs(book, size_limit=0)
    assert "images/clip.gif" in table
    video = tmp_path / "video.mp4"
    video.write_bytes(book.resources.by_path("images/clip.mp4").content)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video)],
        capture_output=True,
        text=True,
        check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p"
    assert (stream["width"], stream["height"]) == (128, 96)
