import re

from library.epub.resources import Resource


FONT_FACE = re.compile(r"@font-face\s*\{[^}]*\}")


def cleanup_panda_line(content: bytes) -> bytes:
    new_content = content.replace(b'font-family: "SerenePanda"', b"font-family: serif").replace(
        b"serif, serif", b"serif"
    )
    assert b"serenepanda" not in new_content.lower()
    return new_content


def cleanup_font_block(content: bytes) -> bytes:
    new_text = re.sub(FONT_FACE, "", content.decode("utf-8"))
    assert "serenepanda" not in new_text.lower()
    return new_text.encode("utf-8")


def de_panda_css_resource(resource: Resource) -> None:
    old_content = resource.content
    if "page_styles" in resource.info.filename:
        resource.content = cleanup_font_block(old_content)
    else:
        resource.content = cleanup_panda_line(old_content)
