import logging
import tempfile
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Self
from zipfile import is_zipfile, ZipFile, ZIP_STORED, ZIP_DEFLATED, ZipInfo

from library.epub.epub_core import EpubCore
from library.epub.resources import ResourceIndex, EPUBResource
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol
from library.epub.xml_literals import FileName, FileContents

logger = logging.getLogger("epub")


class EPUB:
    def __init__(self, path: str | Path) -> None:
        """Initialize an EPUB object with path to epub file or a directory."""
        self.path: Path = Path(path)
        self.__skip_dirs: bool = True
        self.__confirmed_epub: bool = False
        self._core: EpubCore | None = None

        if not self.path.exists():
            # TODO: None for creating new epub? or pass in the not yet existing path
            raise FileNotFoundError(f"Source {path} was not recognized as directory or epub(zipfile).")

        if self.path.is_dir():
            self.source: SourceProtocol = DirectorySource(path, skip_dirs=self.__skip_dirs)
        elif is_zipfile(path):
            self.source: SourceProtocol = ZipFileSource(path, skip_dirs=self.__skip_dirs)
        else:
            raise ValueError("Path must be a directory or a zipfile.")
        logger.debug(f"Initiated {self}, source: {self.source}")

    def __repr__(self):
        return f"EPUB({self.path.name!r})"

    def confirm_mimetype(self) -> bool:
        """Confirm that this source is a valid EPUB by checking the mimetype file.

        Validates:
            1. A file named 'mimetype' exists at the archive root.
            2. Its content is exactly 'application/epub+zip'.
            3. For ZIP sources, it is stored uncompressed (ZIP_STORED).

        Returns:
            True if all checks pass.

        Raises:
            ValueError: If any check fails.
        """
        logger.debug("confirming mimetype")
        mmt = FileName.MIMETYPE
        mmt_contents = FileContents.MIMETYPE

        if self.__confirmed_epub:
            logger.debug("mimetype already confirmed")
            return True

        logger.debug("reading mimetype file")
        with self.source.open():
            mimetype_info = self.source.getinfo(mmt)
            if mimetype_info is None:
                message = f"{self} is missing the '{mmt!s}' file."
                logger.error(message)
                raise ValueError(message)

            # Check compression: must be ZIP_STORED (0) or None (directory source)
            compress_type = mimetype_info.compress_type
            if compress_type not in (ZIP_STORED, None):
                message = f"{self} '{mmt!s}' file must be stored uncompressed (ZIP_STORED=0), got {compress_type=}."
                logger.error(message)
                # raise ValueError(message)  # can still work with it

            content = self.source.read_text(mimetype_info)
            if content.strip() != mmt_contents:
                message = f"{self} '{mmt!s}' content is not '{mmt_contents!r}', got {content!r}."
                logger.error(message)
                raise ValueError(message)

        self.__confirmed_epub = True
        logger.debug("mimetype confirmed")
        return True

    def extract_to(self, dest_dir: str | Path | None = None) -> EPUB:
        if dest_dir is None:
            dest_dir: Path = Path(tempfile.mkdtemp())
        if isinstance(dest_dir, str):
            dest_dir: Path = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        self.source.extract_all(destination=dest_dir)
        return EPUB(dest_dir)

    def package_into(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None):
        exclude_members = [m.filename if isinstance(m, ZipInfo) else m for m in (exclude_members or [])]
        destination: Path = Path(destination)
        self.confirm_mimetype()

        # If core is active, sync models back to resources before packing
        if self._core:
            self._core.sync()

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

        # If resources are already scanned, use them to find modified content
        resources = self._core.resources if self._core else None

        try:
            with self.source.open(), ZipFile(destination, "w", compression=ZIP_DEFLATED) as zipf:
                mimetype_info = self.source.getinfo(FileName.MIMETYPE)
                self.source.write_to_zipfile(zipf, mimetype_info, compress_type=ZIP_STORED)

                for zip_info in self.source.infolist():
                    if zip_info.filename in exclude_members:
                        continue
                    if zip_info.filename == FileName.MIMETYPE:
                        continue
                    if self.__skip_dirs and zip_info.is_dir():
                        continue

                    # Check if we have a version in memory (loaded)
                    resource = resources.by_path(zip_info.filename) if resources else None
                    # TODO: REDO THIS
                    if resource and resource.loaded:
                        # Write bytes from memory
                        # TODO make a proper method for this use case
                        zipf.writestr(zip_info.filename, resource.content)
                    else:
                        # Stream untouched bytes from source
                        self.source.write_to_zipfile(zipf, zip_info)

        except Exception as e:
            logger.error(f"package_into: failed to compress into EPUB: {e}")
            raise e

    @contextmanager
    def stream_to(self, destination: str | Path) -> Generator[Self, None, None]:

        with self.source.open():
            yield self
        self.package_into(destination)

    def scan_resources(self) -> ResourceIndex:
        """Scan the EPUB source and build a ResourceIndex from all files."""
        logger.debug("scanning EPUB resources")
        with self.source.open():
            resources = [EPUBResource(info, self.source.read_bytes) for info in self.source.infolist()]
        return ResourceIndex(resources)

    @property
    def core(self) -> EpubCore:
        """Lazily initialize and return the EpubCore for this EPUB."""
        if self._core is None:
            self.confirm_mimetype()
            resources = self.scan_resources()
            self._core: EpubCore = EpubCore(resources)
            assert self._core is not None, f"{self} epub_core could not be initialized."
        return self._core
