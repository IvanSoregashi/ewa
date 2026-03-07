import re
from pathlib import Path
from typing import Self

import bs4

from library.epub.utils import tag_ids

start = (
    r":A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D"
    r"\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF"
    r"\uF900-\uFDCF\uFDF0-\uFFFD\U00010000-\U000EFFFF"
)
name = start + r"-.0-9\u00B7\u0300-\u036F\u203F-\u2040"

valid_id_pattern = re.compile(f"^[{start}][{name}]*$")


class EPUBId(str):
    """
    A unique identifier for a resource within an EPUB file. Use this class to
    reference epub resources throughout the library using it's manifest id
    rather than its complete filename.

    Typical usage:

    >>> EPUBId("chapter1")
    'chapter1'
    >>> EPUBId("chapter1") == "chapter1"
    True
    >>> EPUBId("chapter 1").valid
    False
    >>> EPUBId.to_valid("chapter 1")
    'chapter_1'

    Args:
        value: The identifier string.
    """

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if the identifier is valid according to the XML specification.

        Returns:
            True if the identifier is valid, False otherwise.
        """

        return bool(valid_id_pattern.match(value))

    @property
    def valid(self) -> bool:
        return self.is_valid(self)

    @classmethod
    def to_valid(cls, value: str) -> Self:
        """
        Convert a string to a valid EPUBId by replacing invalid characters with
        underscores.

        Args:
            value (str): The string to convert.

        Returns:
            EPUBId: A valid EPUBId instance.
        """

        if not value:
            raise ValueError("Identifier cannot be empty.")

        # Replace invalid starting characters
        if not re.match(f"^[{start}]", value[0]):
            value = "_" + value[1:]

        # Replace invalid characters in the rest of the string
        value = re.sub(f"[^{name}]", "_", value)

        return cls(value)


def new_id(base: str | Path, gone: set[str], add_to_gone: bool = True) -> EPUBId:
    """
    Generate a new unique id based on base that is not yet used.

    Args:
        base: The base id to use.
        gone: The set of already used ids.
        add_to_gone: Whether to add the new id to gone.

    Returns:
        The new unique id.

    Raises:
        EPUBError: If no unique id could be generated.
    """

    base = EPUBId.to_valid(str(base))

    if base not in gone:
        if add_to_gone:
            gone.add(base)
        return EPUBId(base)

    for i in range(1, 1 << 16):
        new = f"{base}-{i}"
        if new not in gone:
            if add_to_gone:
                gone.add(new)
            return EPUBId(new)

    raise Exception(f"Exhausted unique id possibilities for {base}")


def new_id_in_tag(base: str | Path, tag: bs4.Tag) -> EPUBId:
    """
    Generate a new unique id based on `base` that is not yet used in tag.

    >>> new_id_in_tag("section", bs4.BeautifulSoup('<div id="section"></div>', "lxml"))
    'section-1'

    Args:
        base: The base id to use.
        tag: The tag to search for existing ids.

    Returns:
        The new unique id.

    Raises:
        EPUBError: If no unique id could be generated.
    """
    ids = tag_ids(tag)
    return new_id(base, ids, False)
