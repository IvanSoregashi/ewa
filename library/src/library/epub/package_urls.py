"""Local package URL handling; archive paths are decoded, URLs are encoded."""

import posixpath
import re
from urllib.parse import quote, unquote, urlsplit


def archive_path(path: str) -> str:
    """Normalize a literal archive file path, rejecting absolute/escaping paths.

    Spaces, Unicode and literal percent signs are allowed. URL delimiters and
    Windows separators/drives are not archive filename syntax for this API.
    """
    if not path or path.startswith("/") or path.endswith(("/", "/.", "/..")):
        raise ValueError(f"Expected an archive-relative file path: {path!r}")
    if any(ord(c) < 32 or ord(c) == 127 or c in "\\:?#" for c in path):
        raise ValueError(f"Invalid archive file path: {path!r}")
    parts = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError(f"Path escapes the archive: {path!r}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise ValueError(f"Expected an archive file path: {path!r}")
    return "/".join(parts)


def path_url(path: str) -> str:
    """Encode a literal archive path for an XML URL attribute."""
    return quote(path, safe="/-._~")


def local_target(base: str, href: str) -> tuple[str, str] | None:
    """Return (decoded archive path, untouched query/fragment suffix), or None for remote URLs.

    Reject ambiguous encoded separators and malformed escapes rather than
    rewriting a URL to a potentially different resource.
    """
    if any(ord(c) < 32 or ord(c) == 127 for c in href):
        raise ValueError(f"Control character in URL: {href!r}")
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None
    path_end = min((i for i in (href.find("?"), href.find("#")) if i >= 0), default=len(href))
    encoded_path, suffix = href[:path_end], href[path_end:]
    if re.search(r"%(?![0-9a-fA-F]{2})|%(?:2f|5c)", encoded_path, re.IGNORECASE):
        raise ValueError(f"Malformed escape or encoded separator in URL: {href!r}")
    decoded = unquote(encoded_path, encoding="utf-8", errors="strict")
    if not decoded:
        return archive_path(base), suffix
    if decoded.startswith("/"):
        raise ValueError(f"Expected a package-relative URL: {href!r}")
    return archive_path(posixpath.join(posixpath.dirname(base), decoded)), suffix


def rebase_href(old_base: str, new_base: str, href: str) -> str:
    target = local_target(old_base, href)
    if target is None:
        return href
    path, suffix = target
    if path == old_base:
        # References to the OPF itself move with that resource.
        return suffix or path_url(posixpath.basename(new_base))
    relative = posixpath.relpath(path, posixpath.dirname(new_base) or ".")
    return path_url(relative) + suffix
