import logging
import tempfile
from collections.abc import Generator, Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Self
from zipfile import is_zipfile, ZIP_STORED

from library.asserts import require
from library.epub.epub_core import EpubCore
from library.epub.errors import EpubSpecificationError, EpubError
from library.epub.resources import ResourceIndex
from library.epub.sink import EpubZipSink
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol
from library.epub.xml_literals import FileContents
from library.epub.media_type import FileName

logger = logging.getLogger("epub")

class EPUB:
    def __init__(self, path: str | Path) -> None:
        self.path: Path = Path(path)
        self.__skip_dirs: bool = True

        self._resources: ResourceIndex | None = None
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

    def is_specification(self, verificators: list[Callable[[EPUB], bool]]):
        return all(verificator(self) for verificator in verificators)

    def require_specification(self, verificators: list[Callable[[EPUB], bool]]):
        for verificator in verificators:
            if not verificator(self):
                raise EpubSpecificationError(verificator.__name__)

    @property
    def resources(self) -> ResourceIndex:
        """Lazily initialize and return the ResourceIndex for this EPUB."""
        if self._resources is None:
            with self.source.open():
                self._resources = ResourceIndex.from_infolist(
                    infolist=self.source.infolist(), stream=self.source.open_stream
                )
        return require(self._resources, f"{self}._resources")

    def get_resources(self, manifest_only: bool = False) -> ResourceIndex:
        if manifest_only:
            return self.core.manifest.manifest_resources
        else:
            return self.resources

    @property
    def core(self) -> EpubCore:
        """Lazily initialize and return the EpubCore for this EPUB."""
        if self._core is None:
            self._core = EpubCore(self.resources)
        return require(self._core, f"{self}._core")

    def extract_to(self, dest_dir: str | Path | None = None) -> EPUB:
        if dest_dir is None:
            dest_dir: Path = Path(tempfile.mkdtemp())
        if isinstance(dest_dir, str):
            dest_dir: Path = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        self.source.extract_all(destination=dest_dir)
        return EPUB(dest_dir)

    def package_into(self, destination: str | Path, manifest_only: bool = False, sort_by_role: bool = False) -> None:
        resolved_destination = self._verify_destination(Path(destination))
        resources = self.get_resources(manifest_only=manifest_only).iter(sort_by_role=sort_by_role)
        try:
            with self.source.open(), EpubZipSink(resolved_destination) as sink:
                for resource in resources:
                    sink.write_resource(resource)
        except Exception as e:
            logger.error(f"package_into: failed to compress into EPUB: {e}")
            raise e
        logger.info(f"{self} successfully packaged into EPUB({destination}).")

    def _verify_destination(self, destination: Path) -> Path:
        if destination.suffix.lower() != ".epub":
            if not destination.is_dir():
                raise NotADirectoryError(f"Path {destination} is neither a directory nor a epub.")
            destination = destination / self.path.name
        if destination.exists():
            raise FileExistsError(f"File {destination} already exists.")
        if not destination.parent.exists():
            raise FileNotFoundError(f"Directory {destination.parent} does not exist.")
        return destination

    @contextmanager
    def stream_to(self, destination: str | Path) -> Generator[Self, None, None]:
        try:
            with self.source.open():
                yield self
        except EpubError:
            logger.error(f"{self} will not be packaged to {destination!r}.")
        else:
            self.package_into(destination)
