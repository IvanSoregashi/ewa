import logging
from pathlib import Path
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
            raise FileNotFoundError(f"Source {path} was not recognized as directory or epub(zipfile).")

