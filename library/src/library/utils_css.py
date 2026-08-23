import re
from typing import Generator


FONT_FACE = re.compile(r"@font-face\s*\{[^}]*\}")

css_url_pattern: re.Pattern[bytes] = re.compile(rb'url\s*\(\s*([\'"]?)(.*?)\1\s*\)', re.IGNORECASE)


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


def parse_css_urls(content: bytes) -> Generator[str, None, None]:
    for match in css_url_pattern.finditer(content):
        yield match.group(2).decode("utf-8")


def replace_css_url(content: bytes, old: str, new: str):
    old_bytes = old.encode("utf-8")
    new_bytes = new.encode("utf-8")

    def replacement(match: re.Match[bytes]) -> bytes:
        quote = match.group(1)
        original_url = match.group(2)
        if original_url == old_bytes:
            return b"url(" + quote + new_bytes + quote + b")"
        return match.group(0)

    return css_url_pattern.sub(replacement, content)


def _delete_css_block(content: bytes, url: str) -> bytes:
    """EXPERIMENTAL"""
    block_pattern = re.compile(
        rb'(?is)[^}]*?\{[^{}]*?url\s*\(\s*([\'"]?)' + re.escape(url.encode("utf-8")) + rb"\1\s*\)[^{}]*?\}"
    )
    return block_pattern.sub(b"", content)
