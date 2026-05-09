import re
from collections.abc import Generator

css_url_pattern: re.Pattern[bytes] = re.compile(rb'url\s*\(\s*([\'"]?)(.*?)\1\s*\)', re.IGNORECASE)


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
