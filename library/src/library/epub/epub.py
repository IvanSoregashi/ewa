import logging
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Self
from zipfile import is_zipfile

from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol

logger = logging.getLogger(__name__)


class EPUB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.source: SourceProtocol | None = None
        if self.path.is_dir():
            self.source = DirectorySource(path)
        elif is_zipfile(path):
            self.source = ZipFileSource(path)
        if self.source is None:
            # TODO: None for creating new epub? or pass in the not yet existing path
            raise FileNotFoundError(f"Source {path} was not recognized as directory or epub(zipfile).")

    def extract_to(self, destination: str | Path | None = None) -> EPUB:
        if self.source is None:
            raise ValueError("source is not set")
        if destination is None:
            destination = Path(tempfile.mkdtemp())
        destination.mkdir(parents=True, exist_ok=True)
        self.source.extract_all(destination=destination)
        return EPUB(destination)

    @contextmanager
    def stream_to(self, destination: str | Path) -> Generator[Self, None, None]: ...
