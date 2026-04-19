import re
import unicodedata
from datetime import datetime, timezone
from typing import overload


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
