import re
from pathlib import Path

from library.epub.resources import Resource

FONT_FACE = re.compile(r"@font-face\s*\{[^}]*\}")


def cleanup_panda_line(content: bytes) -> bytes:
    return (
        content.decode("utf-8")
        .replace('font-family: "SerenePanda"', "font-family: serif")
        .replace("serif, serif", "serif")
        .encode("utf-8")
    )


def cleanup_font_block(content: bytes) -> bytes:
    return re.sub(FONT_FACE, "", content.decode("utf-8")).encode("utf-8")


def de_panda_css_resource(res: Resource) -> None:
    old_content = res.content
    if "page_styles" in res.info.filename:
        res.content = cleanup_font_block(old_content)
    else:
        res.content = cleanup_panda_line(old_content)

    if res.content != old_content:
        res.is_modified = True
