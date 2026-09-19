from io import BytesIO
from zipfile import ZipInfo

from lxml import etree
from library.epub.resources import Resource
from epub.recipe_html import VideoTagInfo, replace_gifs_with_videos

GIF_CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter</title></head>
  <body>
    <p>before</p>
    <img src="images/old.gif" alt="animation"/>
    <img src="images/other.png" alt="kept"/>
    <p>after</p>
  </body>
</html>"""


def html_resource(markup: str, filename: str = "OEBPS/text/chapter.xhtml") -> Resource:
    data = markup.encode("utf-8")
    info = ZipInfo(filename)
    info.file_size = len(data)
    return Resource(info=info, stream_bytes=lambda i: BytesIO(data))


def make_video_table(**overrides) -> dict[str, VideoTagInfo]:
    return {
        "OEBPS/text/images/old.gif": VideoTagInfo(
            video_path="OEBPS/text/images/old.mp4",
            poster_path="OEBPS/text/images/old.jpg",
            width=768,
            height=1152,
            alt="old.gif",
            **overrides,
        )
    }


def test_replace_gifs_with_videos_replaces_matching_img():
    resource = html_resource(GIF_CHAPTER)

    replaced = replace_gifs_with_videos(resource, make_video_table())

    assert replaced == 1
    content = resource.content
    assert b'<video src="images/old.mp4" poster="images/old.jpg"' in content
    assert b'controls="controls"' in content
    assert b'preload="metadata"' in content
    assert b'width="768"' in content and b'height="1152"' in content
    assert b'<source src="images/old.mp4" type="video/mp4"/>' in content
    assert b'<img src="images/old.jpg" alt="old.gif"/>' in content
    assert b'src="images/other.png"' in content  # unmapped img untouched
    assert b'src="images/old.gif"' not in content  # gif reference gone (alt label may keep the name)
    etree.fromstring(content)  # output stays valid parseable XML


def test_replace_gifs_with_videos_no_match_leaves_document_valid():
    resource = html_resource(GIF_CHAPTER)

    replaced = replace_gifs_with_videos(resource, {})

    assert replaced == 0
    assert b"<img" in resource.content
    assert b"<video" not in resource.content
    etree.fromstring(resource.content)
