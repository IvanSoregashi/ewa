import io
from pathlib import Path
from typing import IO, Self, override
from zipfile import ZipInfo

import bs4

from library.epub.utils import strip_fragment
from library.epub.zip_utils import info_to_zipinfo


class Resource:
    """
    Base class for all resources (i.e. files) in an EPUB file.

    >>> resource = Resource(b"Hello, world!", "misc/hello.txt")
    >>> resource.filename
    'misc/hello.txt'
    >>> resource.content
    b'Hello, world!'

    Args:
        file: A file-like object or bytes containing the resource data.
        info: A ZipInfo object or a string/Path representing the location
            of the resource in the EPUB archive.
    """

    def __init__(self, file: IO[bytes] | bytes, info: ZipInfo | str | Path) -> None:
        self.zipinfo: ZipInfo = info_to_zipinfo(info)
        self._file: IO[bytes] = io.BytesIO(file) if isinstance(file, bytes) else file
        self._content: bytes | None = None

    @classmethod
    def from_path(cls, filename: str | Path, info: str | Path | ZipInfo) -> Self:
        """
        Create a Resource from a file on disk.

        Args:
            filename: The path to the file on disk.
            info: A ZipInfo object or a string/Path representing the location
                of the resource in the EPUB archive.
        """
        file = open(filename, "rb")
        if not isinstance(info, ZipInfo):
            info = ZipInfo.from_file(filename, info, strict_timestamps=False)
        return cls(file, info)

    @override
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.filename})"

    def on_content_change(self) -> None:
        """Hook called when the content of this resource changes."""

    @property
    def filename(self) -> str:
        """
        The absolute path to this resource in the EPUB archive. When setting,
        any fragment will be removed.
        """
        return self.zipinfo.filename

    @filename.setter
    def filename(self, value: str) -> None:
        self._set_filename(value)

    def _set_filename(self, value: str) -> None:
        self.zipinfo.filename = strip_fragment(value)

    def get_content(self, cache: bool = True) -> bytes:
        """
        Get the content of this resource. If this content hasn't been
        cached yet and `cache` is False, the content will be read
        directly from the underlying file without storing it in memory.

        Args:
            cache: Whether to cache the content in memory for future access.
            Defaults to True.

        Raises:
            ClosedEPUBError: If this resource has been closed.
        """

        self.check_closed()
        content = self._content
        if content is None:
            content = self._file.read()
            __ = self._file.seek(0)
            if cache:
                self._content = content

        return content

    @property
    def content(self) -> bytes:
        """
        The contents of this resource.

        Raises:
            ClosedEPUBError: When getting the content, if this resource has been
                closed.
        """

        return self.get_content()

    @content.setter
    def content(self, value: bytes) -> None:
        self.check_closed()
        self._set_content(value)

    def _set_content(self, value: bytes, content_change: bool = True) -> None:
        self._content = value
        if content_change:
            self.on_content_change()

    def get_title(self) -> str:
        """
        Get a human-readable title for this resource.
        """
        return self.filename

    @property
    def closed(self) -> bool:
        """Whether this resource has been closed."""
        return self._file.closed

    def check_closed(self) -> None:
        """
        Raise an error if this resource has been closed.

        Raises:
            ClosedEPUBError: If this resource has been closed.
        """
        if self.closed:
            raise IOError(f"Using resource {self.filename} after closing")

    def close(self) -> None:
        """Close this resource and free any associated resources."""
        del self._content
        self._content = None
        self._file.close()


class XMLResource[S: bs4.BeautifulSoup = bs4.BeautifulSoup](Resource):
    """
    A resource that is an XML file. Provides a `soup` property that contains a
    BeautifulSoup representation of the XML content.

    Args:
        file: A file-like object or bytes containing the resource data.
        info: A ZipInfo object or a string/Path representing the location
            of the resource in the EPUB archive.
    """

    soup_class: type[S] = bs4.BeautifulSoup  # type: ignore[reportAssignmentType]

    def __init__(self, file: IO[bytes] | bytes, info: ZipInfo | str | Path) -> None:
        super().__init__(file, info)
        self._soup: None | S = None

    @property
    def soup(self) -> S:
        """
        A BeautifulSoup representation of the XML content of this resource.
        """
        if self._soup is None:
            self._soup = self.soup_class(self.content, "xml")
        return self._soup

    @soup.setter
    def soup(self, value: S) -> None:
        self._set_soup(value)

    def _set_soup(self, value: S) -> None:
        self._soup = value

    @override
    def get_content(self, cache: bool = True) -> bytes:
        if self._soup is not None:
            self._set_content(self._soup.encode(), content_change=False)
        return super().get_content()

    @override
    def on_content_change(self) -> None:
        super().on_content_change()
        del self._soup
        self._soup = None

    @override
    def get_title(self) -> str:
        if self.soup.title and self.soup.title.string:
            return self.soup.title.string
        return super().get_title()
