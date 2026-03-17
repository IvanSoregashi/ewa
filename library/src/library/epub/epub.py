import logging
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Self
from zipfile import is_zipfile, ZipFile, ZIP_STORED, ZIP_DEFLATED

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
        self._confirmed_epub: bool = False

    def ensure_epub(self):
        if not self._confirmed_epub:
            # TODO mimetype confirmation
            return True
        return True

    def extract_to(self, dest_dir: str | Path | None = None) -> EPUB:
        if dest_dir is None:
            dest_dir = Path(tempfile.mkdtemp())
        dest_dir.mkdir(parents=True, exist_ok=True)
        self.source.extract_all(destination=dest_dir)
        return EPUB(dest_dir)

    def package_into(self, destination: str | Path):
        destination = Path(destination)
        self.ensure_epub()
        if destination.suffix.lower() != ".epub":
            if destination.is_dir():
                destination = destination / self.path.name
            else:
                raise NotADirectoryError(f"Path {destination} is neither a directory nor a epub.")
        if destination.suffix.lower() == ".epub":
            if destination.exists():
                raise FileExistsError(f"File {destination} already exists.")
            if not destination.parent.exists():
                raise FileNotFoundError(f"Directory {destination.parent} does not exist.")

        try:
            with self.source.open(), ZipFile(destination, "w", compression=ZIP_DEFLATED) as zipf:
                mimetype_info = self.source.getinfo("mimetype")
                self.source.write_to_zipfile(zipf, mimetype_info, compress_type=ZIP_STORED)

                for zip_info in self.source.infolist():
                    # TODO: ZIP_STORED for images (already compressed)
                    # TODO: BUFFERED shutil.copyfileobj for big files
                    if zip_info.filename == "mimetype":
                        continue
                    self.source.write_to_zipfile(zipf, zip_info)
        except Exception as e:
            logger.error(f"package_into: failed to compress into EPUB: {e}")
            raise e

    @contextmanager
    def stream_to(self, destination: str | Path) -> Generator[Self, None, None]: ...
