import os
import posixpath
from pathlib import Path
from typing import TypeVar

strPath = str | Path
StrPathT = TypeVar("StrPathT", str, Path, strPath)


def split_fragment(href: StrPathT) -> tuple[StrPathT, str | None]:
    """
    Given an href, split it into the part before the fragment
    identifier (#...) and the fragment identifier itself.

    >>> split_fragment("chapter1.xhtml#section2")
    ('chapter1.xhtml', 'section2')
    >>> split_fragment("chapter1.xhtml")
    ('chapter1.xhtml', None)
    >>> split_fragment("#")
    ('', '')

    Args:
        href: The href to split.
    Returns:
        A tuple (name, fragement) of the part before the fragment and the
        fragment itself (or None).
    """
    cls = type(href)

    values = str(href).split("#", 1)
    if len(values) < 2:
        return cls(values[0]), None
    return cls(values[0]), values[1]


def strip_fragment(href: StrPathT) -> StrPathT:
    """
    Given an href, return the part before the fragment identifier (#...).

    >>> strip_fragment("chapter1.xhtml#section2")
    'chapter1.xhtml'
    >>> strip_fragment("chapter1.xhtml")
    'chapter1.xhtml'
    >>> strip_fragment("#section2")
    ''

    Args:
        href: The href to strip.

    Returns:
        The part before the fragment.
    """

    return split_fragment(href)[0]


def get_fragment(href: strPath) -> str | None:
    """
    Given an href, return the fragment identifier (#...) or None if
    there is none.

    >>> get_fragment("chapter1.xhtml#section2")
    'section2'
    >>> get_fragment("chapter1.xhtml") is None
    True
    >>> get_fragment("#")
    ''

    Args:
        href: The href to get the fragment from.

    Returns:
        The fragment or None.
    """

    return split_fragment(str(href))[1]


def normalize_path(path: StrPathT) -> StrPathT:
    """
    Normalize a path by removing ..'s

    >>> normalize_path("a/b/../c")
    'a/c'

    Args:
        path: The path to normalize.

    Returns:
        The normalized path.
    """
    cls = type(path)
    absolute = os.path.normpath(path)
    return cls(absolute)


def get_absolute_href(origin_href: strPath, href: StrPathT) -> StrPathT:
    """
    Get absolute href from an origin and a relative href.

    >>> get_absolute_href("OEBPS/chapter1.xhtml", "../images/pic.png")
    'images/pic.png'

    Args:
        origin_href: The origin.
        href: The relative href.

    Returns:
        The absolute href.
    """
    cls = type(href)

    if str(href).startswith("#"):
        path = Path(f"{origin_href}{href if href != '#' else ''}")
    else:
        path = Path(origin_href).parent / Path(href)

    return cls(normalize_path(path))


def get_relative_href(relative_to: strPath, absolute_href: StrPathT) -> StrPathT:
    """
    Get relative href from an absolute href and a base href.

    >>> get_relative_href("OEBPS/chapter1.xhtml", "OEBPS/images/pic.png")
    'images/pic.png'

    Args:
        relative_to: The base href.
        absolute_href: The absolute href.

    Returns:
        The relative href.
    """
    cls = type(absolute_href)

    if strip_fragment(absolute_href) == strip_fragment(relative_to):
        fragment = get_fragment(absolute_href)
        path = Path(f"#{fragment if fragment is not None else ''}")
    else:
        path = Path(absolute_href).relative_to(Path(relative_to).parent, walk_up=True)

    return cls(path)


# os.path.relpath - relative path including the walkback os.path.relpath(target, start)
# os.path.abspath - can resolve walkbacks - /dir/../dir1/1


def get_absolute_posix_href(href: str, source_file: str) -> str:
    """Resolve a manifest href (relative to OPF by default) to an absolute EPUB path."""
    href = strip_fragment(href)
    source_dir = posixpath.dirname(source_file)
    if source_dir:
        href = posixpath.join(source_dir, href)
    return href
