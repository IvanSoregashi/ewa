import zipfile
from pathlib import Path
from typing import IO, Literal, Protocol, override
from zipfile import ZipInfo


class SourceProtocol(Protocol):
    """
    Protocol for a source of EPUB data.
    """

    def getinfo(self, name: str) -> ZipInfo:
        """
        Get a ZipInfo object for the given name.

        Args:
            name: The name of the item to get info for.

        Returns:
            A ZipInfo object for the given name.
        """
        ...

    def infolist(self) -> list[ZipInfo]:
        """
        Returns a list of all ZipInfo objects in the source.
        """
        ...

    def open(
        self,
        name: str | ZipInfo,
        mode: Literal["r", "w"] = "r",
        pwd: bytes | None = None,
        *,
        force_zip64: bool = False,
    ) -> IO[bytes]:
        """
        Open a file in the source.

        Args:
            name: The name of the item to open, or a ZipInfo object.
            mode: The mode to open the file in..
            pwd: The password to use for encrypted files.
            force_zip64: Whether to force ZIP64 extensions.

        Returns:
            A file-like object for the opened item.
        """
        ...

    def read(self, name: str) -> bytes:
        """
        Read contents of a file in the source.

        Args:
            name: The name of the file to read.

        returns bytes of the file.
        """
        ...

    def close(self) -> None:
        """Close this source."""
        ...

    @property
    def closed(self) -> bool:
        """Returns whether this source is closed."""
        ...


class SinkProtocol(Protocol):
    """Protocol for a sink of EPUB data."""

    def writestr(
        self,
        zinfo_or_arcname: str | ZipInfo,
        data: bytes | str,
        compress_type: int | None = None,
        compresslevel: int | None = None,
    ) -> None:
        """
        Write a string or bytes to the sink.

        Args:
            zinfo_or_arcname: The name of the item to write, or a ZipInfo object.
            data: The data to write.
            compress_type: The compression type to use.
            compresslevel: The compression level to use.
        """
        ...


class DirectorySource(SourceProtocol):
    """
    An EPUB source that reads the book from a directory on the filesystem
    (an 'unzipped' EPUB).

    Args:
        path: The path to the directory containing the EPUB files.
    """

    def __init__(self, path: str | Path) -> None:
        self.path: Path = Path(path)
        if not self.path.is_dir():
            raise NotADirectoryError(f"'{path}' is not a directory")
        self._closed: bool = False

    def _to_zipinfo(self, name: str) -> ZipInfo:
        return ZipInfo.from_file(
            self.path / name,
            arcname=name,
            strict_timestamps=False,
        )

    @override
    def getinfo(self, name: str | Path) -> ZipInfo:
        target = self.path / name
        if target.is_file():
            return self._to_zipinfo(str(name))
        raise KeyError(f"There is no item named '{name}' in the folder")

    @override
    def infolist(self) -> list[ZipInfo]:
        return [
            self._to_zipinfo(str(file.relative_to(self.path))) for file in self.path.rglob("*") if not file.is_dir()
        ]

    @override
    def open(
        self,
        name: str | Path | ZipInfo,
        mode: Literal["r", "w"] = "r",
        pwd: bytes | None = None,
        *,
        force_zip64: bool = False,
    ) -> IO[bytes]:
        if isinstance(name, ZipInfo):
            filename = self.path / name.filename
        else:
            filename = self.path / name

        return open(filename, mode + "b")

    @override
    def read(self, name: str) -> bytes:
        filepath = self.path / name
        return filepath.read_bytes()

    def write(self, content: str | bytes, name: str) -> int:
        filepath = self.path / name
        if isinstance(content, str):
            return filepath.write_text(content)
        if isinstance(content, bytes):
            return filepath.write_bytes(content)
        return 0

    @override
    def close(self) -> None:
        self._closed = True

    @property
    @override
    def closed(self) -> bool:
        return self._closed


class DirectorySink(SinkProtocol):
    """
    An EPUB sink that writes the book to a directory on the filesystem
    (as an 'unzipped' EPUB).

    Args:
        path: The path to the directory to write the EPUB files to.
    """

    def __init__(self, path: str | Path) -> None:
        self.path: Path = Path(path)
        if not self.path.is_dir():
            raise NotADirectoryError(f"'{path}' is not a directory")

    @override
    def writestr(
        self,
        zinfo_or_arcname: str | Path | ZipInfo,
        data: bytes | str,
        compress_type: int | None = None,
        compresslevel: int | None = None,
    ) -> None:
        if isinstance(zinfo_or_arcname, ZipInfo):
            filename = zinfo_or_arcname.filename
        else:
            filename = zinfo_or_arcname

        full_path = self.path / filename

        if str(full_path.parent) != ".":
            full_path.parent.mkdir(exist_ok=True, parents=True)

        mode = "w" if isinstance(data, str) else "wb"
        with open(full_path, mode) as f:
            __ = f.write(data)


class ZipFile(zipfile.ZipFile):
    """
    A ZipFile subclass that implements SourceProtocol
    """

    @property
    def closed(self) -> bool:
        return self.fp is None or self.fp.closed
