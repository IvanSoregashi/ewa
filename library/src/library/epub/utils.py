import enum
import operator
import os.path
import re
import types
import typing
import unicodedata
from collections.abc import Generator, Iterable
from datetime import datetime, timezone
from functools import reduce
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import UnionType
from typing import cast, overload

import bs4


def normalize_path[T: (str, Path, str | Path)](path: T) -> T:
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
    # Resolve ..'s
    absolute = os.path.normpath(path)
    return cls(absolute)


def get_absolute_href[T: (str, Path, str | Path)](origin_href: str | Path, href: T) -> T:
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


def get_relative_href[T: (str, Path, str | Path)](relative_to: str | Path, absolute_href: T) -> T:
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


@overload
def parse_int(value: str) -> int | None: ...
@overload
def parse_int(value: None) -> None: ...


def parse_int(value: str | None) -> int | None:
    """
    Lenient integer parsing

    >>> parse_int("42")
    42
    >>> parse_int("  42  xxx")
    42
    >>> parse_int("xxx") is None
    True
    >>> parse_int(None) is None
    True

    Args:
        value: The value to parse.

    Returns:
        The parsed integer or None if parsing failed.
    """
    if value is None:
        return None

    value = "".join([val for val in value if val.isdigit() or val in "-."])
    value = value.split(".", 1)[0]  # Remove decimal part
    try:
        return int(value)
    except ValueError:
        return None


def tag_ids(tag: bs4.Tag) -> set[str]:
    """
    Return set of all ids in a tag.

    Args:
        tag: The tag to search.
    """
    return {attr_to_str(t["id"]) for t in tag.find_all(id=True)}


def split_fragment[T: (str, Path, str | Path)](href: T) -> tuple[T, str | None]:
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


def strip_fragment[T: (str, Path, str | Path)](href: T) -> T:
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


def get_fragment(href: str | Path) -> str | None:
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


def slugify(value: str) -> str:
    """
    Convert to ASCII. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.

    Adapted from django's utils.text.

    >>> slugify("Hello, World!")
    'hello-world'

    Args:
        value: The value to slugify.

    Returns:
        The slugified value.
    """
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


class ResolutionType(enum.Enum):
    """
    Strategy for converting a list of BeautifulSoup attribute values into a
    single string.
    """

    JOIN = enum.auto()
    FIRST = enum.auto()


@overload
def attr_to_str(
    value: str | list[str],
    resolution_type: ResolutionType = ResolutionType.JOIN,
) -> str: ...


@overload
def attr_to_str(
    value: str | list[str] | None,
    resolution_type: ResolutionType = ResolutionType.JOIN,
) -> str | None: ...


def attr_to_str(
    value: str | list[str] | None,
    resolution_type: ResolutionType = ResolutionType.JOIN,
) -> str | None:
    """
    Resolve a BeautifulSoup attribute value into a string.

    Args:
        value: The attribute value to resolve.
        resolution_type: The strategy to use for resolving lists.
    """
    if value is None:
        return None

    if isinstance(value, list):
        match resolution_type:
            case ResolutionType.JOIN:
                return " ".join(value)
            case ResolutionType.FIRST:
                return value[0]

    return value


def get_actual_tag_position(
    tag: bs4.Tag,
    position: int,
    name: str | None = None,
) -> int:
    """
    Given a tag `tag` and a position `i`, return the index `ret` of
    `position`-th child of tag (i.e. disregarding NavigableString
    children of tag). If name is given, consider only children that are
    tags with that name. If `position` is out of bounds, return position for
    last child + 1.

    Args:
        tag: The tag to search.
        position: The position of the child to find.
        name: The name of the child tags to consider.

    Returns:
        The index of the `position`-th child tag.
    """

    tags = list(tag.find_all(name, recursive=False))

    if position >= len(tags):
        return len(list(tag.children))

    sucessor = tags[position]
    return tag.index(sucessor)


def get_attributes(
    parent: bs4.Tag,
    attributes: Iterable[str],
) -> Generator[tuple[bs4.Tag, str, str]]:
    """
    Given a parent tag and a list of attribute names, yield tuples (child,
    attr, value) where:
        - child is a child of tag containing some of the attributes;
        - attr is the name of the attribute; and
        - value is the value of that attribute in this child.
    If a child has more than one attribute in the given attributes, yield one tuple per attribute.

    Args:
        parent: The parent.
        attributes: The attribute names to look for.
    """
    selector = ", ".join(f"[{attr.replace(':', '|')}]" for attr in attributes)

    for tag in parent.select(selector):
        for attr in attributes:
            value = attr_to_str(tag.get(attr))
            if value is not None:
                yield tag, attr, value


def datetime_to_str(dt: datetime) -> str:
    """
    Convert a datetime to a string in ISO8601 format in utc timezone, using
    trailing Z instead of +00:00.

    Args:
        dt: The datetime to convert.

    Returns:
        The ISO8601 string representation of the datetime.
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()

    dt = dt.astimezone(timezone.utc)

    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def get_epublib_version() -> str | None:
    """
    Returns the version of epublib if installed as a package. If not found,
    return None.
    """
    try:
        return version("epublib")
    except PackageNotFoundError:
        return None


def strip_type_parameters[T: UnionType | object](typ: type[T]) -> type[T]:
    """
    Strip parameters of type hints, making them suitable for usage
    with isinstance and issubclass checks. If the type is a Literal, return the
    types of those literals as a UnionType.

    >>> strip_type_parameters(list[int])
    <class 'list'>
    >>> strip_type_parameters(typing.Literal["a", 1])
    str | int

    Args:
        typ: The type to strip.

    Returns:
        The stripped type.
    """

    origin: type[T] = typing.get_origin(typ) or typ

    if origin is UnionType or origin is typing.Union:  # type: ignore[reportDeprecated]
        if origin is typing.Union:  # type: ignore[reportDeprecated]
            origin = typ

        origin = cast(
            type[T],
            operator.or_(*(strip_type_parameters(arg) for arg in cast(tuple[type[T], ...], typing.get_args(typ)))),
        )
    elif origin is typing.Literal:
        types: set[type[T]] = {type(option) for option in cast(tuple[type[T], ...], typing.get_args(typ))}
        if len(types) == 1:
            origin = types.pop()
        else:
            origin = cast(type[T], reduce(operator.or_, types))

    return origin


def remove_optional_type[T: UnionType | object](typ: T) -> T:
    """
    Return the first type from list of types in a UnionType that is not
    NoneType. This make the union ready for usage as first argument of issubclass.

    >>> remove_optional_type(int | None)
    <class 'int'>
    >>> remove_optional_type(None | str)
    <class 'str'>

    Args:
        typ: The union type to remove None from options.

    Returns:
        The type without None as option.
    """

    if not isinstance(typ, UnionType):
        return typ

    return next(arg for arg in typing.get_args(typ) if arg is not types.NoneType)  # type: ignore[reportAny]
