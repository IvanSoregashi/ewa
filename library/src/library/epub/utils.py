import re
import unicodedata
from datetime import datetime, timezone
from typing import overload

import logging
from hashlib import md5
from struct import unpack

from library.database.constants import SQLITE_MAX_INT

logger = logging.getLogger(__name__)


def to_hash(data: str | bytes) -> bytes:
    if isinstance(data, str):
        data: bytes = data.encode("utf-8")
    return md5(data).digest()


def to_hex_hash(data: str | bytes) -> str:
    if isinstance(data, str):
        data: bytes = data.encode("utf-8")
    return md5(data).hexdigest()


def string_to_int_hash64(data: str | bytes) -> int:
    """returns a 64-bit integer hash"""
    return int(to_hex_hash(data), 16) % SQLITE_MAX_INT


def string_to_int_hash(data: str | bytes) -> int:
    """
    Generates a 64-bit signed integer hash from a string,
    utilizing the full SQLite INTEGER range (positive and negative).
    """
    # 1. Generate the 128-bit MD5 hash
    hash_digest = to_hash(data)

    # 2. Unpack the first 8 bytes (64 bits) of the hash as a signed 64-bit integer
    # '>' means big-endian, 'q' means signed long long (64-bit integer)
    # This automatically handles negative numbers when the sign bit is set.
    (signed_64bit_int,) = unpack(">q", hash_digest[:8])
    return signed_64bit_int


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


def ts_to_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def bt_to_mb(size_in_bytes: int) -> str:
    return f"{size_in_bytes / (1024 * 1024):.2f} mb"
