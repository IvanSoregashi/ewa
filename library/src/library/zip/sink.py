from collections.abc import Iterable
from copy import copy
from pathlib import Path
from typing import BinaryIO, Self
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from library.asserts import require


class ZipSink:
    """Write ZIP entries incrementally inside a context manager."""

    def __init__(self, path: str | Path | BinaryIO):
        self.path = path
        self._zip_file: ZipFile | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path!r})"

    @property
    def zip_file(self) -> ZipFile:
        return require(self._zip_file, f"{self}._zip_file")

    def write_chunks(self, member: str | ZipInfo, chunks: Iterable[bytes]) -> None:
        """Write chunks of unknown total size, allowing empty chunks.

        ZipInfo supplies metadata and compression; a name uses archive defaults.
        The caller's ZipInfo is left unchanged. If iteration fails, the archive
        retains the partially written entry. ZIP64 permits entries over 2 GiB.
        """
        info = copy(member) if isinstance(member, ZipInfo) else member
        with self.zip_file.open(info, "w", force_zip64=True) as destination:
            for chunk in chunks:
                destination.write(chunk)

    def write_stream(self, member: str | ZipInfo, stream: BinaryIO, *, chunk_size: int = 65536) -> None:
        """Copy from the stream's current position without seeking or closing it."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.write_chunks(member, iter(lambda: stream.read(chunk_size), b""))

    def __enter__(self) -> Self:
        if self._zip_file is not None:
            raise ValueError("ZipSink is already open")
        self._zip_file = ZipFile(self.path, "w", compression=ZIP_DEFLATED)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.zip_file.close()
        finally:
            self._zip_file = None
