"""End-to-end test for the giant-gif recipe: conversion, rename, poster
resource + manifest item, and chapter video-tag rewriting - on a synthetic
epub (same pattern as test_recipe_package / test_verification)."""

import io
import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from epub.recipe_gif import convert_giant_gifs, rewrite_gif_chapters
from library.epub.epub import EPUB
from library.epub.media_type import FileName, MediaType

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="system ffmpeg required")


def make_animated_gif(size: int = 64, frames: int = 3) -> bytes:
    images = [Image.new("RGB", (size, size), (i * 60 % 256, 100, 150)) for i in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="GIF", save_all=True, append_images=images[1:], duration=100, loop=0)
    return buffer.getvalue()


def make_giant_animated_gif(target_size: int = 5 * 1024 * 1024 + 1, size: int = 300) -> bytes:
    probe = Image.effect_noise((size, size), 64)
    single = io.BytesIO()
    probe.save(single, format="GIF")
    frames_needed = min(500, target_size // max(single.tell(), 1) + 2)
    frames = [Image.effect_noise((size, size), 64).convert("RGB") for _ in range(frames_needed)]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=40, loop=0)
    assert len(buffer.getvalue()) > target_size
    return buffer.getvalue()


def build_epub(path: Path, small_gif: bytes, giant_gif: bytes) -> None:
    # opf standardized to the archive root: manifest hrefs coincide with
    # archive paths (the contract EpubManifest.from_package relies on)
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>t</dc:title><dc:identifier id="id">x</dc:identifier><dc:language>en</dc:language></metadata>
 <manifest>
  <item id="ch" href="text/chapter.xhtml" media-type="application/xhtml+xml"/>
  <item id="small" href="images/small.gif" media-type="image/gif"/>
  <item id="giant" href="images/giant.gif" media-type="image/gif"/>
 </manifest>
 <spine><itemref idref="ch"/></spine>
</package>"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    chapter = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
 <head><title>t</title></head>
 <body>
  <p><img src="../images/small.gif" alt="s"/></p>
  <p><img src="../images/giant.gif" alt="g"/></p>
 </body>
</html>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(FileName.MIMETYPE, "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("content.opf", opf)
        z.writestr("text/chapter.xhtml", chapter)
        z.writestr("images/small.gif", small_gif)
        z.writestr("images/giant.gif", giant_gif)


@requires_ffmpeg
def test_convert_giant_gifs_end_to_end(tmp_path: Path):
    path = tmp_path / "book.epub"
    build_epub(path, make_animated_gif(), make_giant_animated_gif())
    epub = EPUB(path)

    table = convert_giant_gifs(epub)

    # only the giant gif converted; the small one untouched
    assert set(table) == {"images/giant.gif"}
    info = table["images/giant.gif"]
    assert info.video_path == "images/giant.mp4"
    assert info.poster_path == "images/giant.jpg"

    renamed = epub.resources.by_path("images/giant.mp4")
    assert renamed is not None
    assert renamed.media_type.value == "video/mp4"
    assert renamed.content[4:8] == b"ftyp"

    poster = epub.resources.by_path("images/giant.jpg")
    assert poster is not None
    assert poster.content[:2] == b"\xff\xd8"

    kept = epub.resources.by_path("images/small.gif")
    assert kept is not None and kept.media_type is MediaType.IMAGE_GIF

    # manifest: gif item renamed, poster item added
    opf = epub.core.package_resource.content.decode()
    assert 'href="images/giant.mp4" media-type="video/mp4"' in opf
    assert 'href="images/giant.jpg" media-type="image/jpeg"' in opf
    assert "images/giant.gif" not in opf

    # chapter rewriting
    replaced = rewrite_gif_chapters(epub, table)
    assert replaced == 1
    chapter = epub.resources.by_path("text/chapter.xhtml").content.decode()
    assert "<video" in chapter and 'src="../images/giant.mp4"' in chapter
    assert "images/giant.gif" not in chapter
