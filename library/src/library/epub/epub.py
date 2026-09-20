import io
import logging
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Self
from zipfile import is_zipfile

from library.asserts import require
from library.epub.errors import EpubError
from library.epub.media_type import EpubRole
from library.epub.package import EpubPackage
from library.epub.resources import ResourceIndex, IndexInfo
from library.epub.sink import EpubZipSink
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol
from library.utils import verify_destination

logger = logging.getLogger("epub")


class EPUB:
    def __init__(self, path: str | Path) -> None:
        self.path: Path = Path(path)
        self.__skip_dirs: bool = True

        self._resources: ResourceIndex | None = None
        self._package: EpubPackage | None = None
        self._info: EpubInfo | None = None

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

    @property
    def resources(self) -> ResourceIndex:
        """Lazily initialize and return the ResourceIndex for this EPUB."""
        if self._resources is None:
            with self.source.open():
                self._resources = ResourceIndex.from_infolist(
                    infolist=self.source.infolist(), stream=self.source.open_stream
                )
        return require(self._resources, f"{self}._resources")

    @property
    def package(self) -> EpubPackage:
        """Lazily discover the package from this EPUB's resources."""
        if self._package is None:
            self._package = EpubPackage.from_resources(self.resources)
        return self._package

    def extract_to(self, dest_dir: str | Path | None = None) -> EPUB:
        if dest_dir is None:
            dest_dir: Path = Path(tempfile.mkdtemp())
        if isinstance(dest_dir, str):
            dest_dir: Path = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        self.source.extract_all(destination=dest_dir)
        return EPUB(dest_dir)

    def package_into(
        self,
        destination: str | Path | io.BytesIO,
        sort_by_role: bool = True,
    ) -> None:
        """Package the current state into a new epub archive.

        destination may be:
            - a filepath (str | Path): the archive is assembled in an internal
              buffer first and only written to disk on success, so a failure
              mid-packaging never leaves a truncated file behind;
            - an open binary file object: the archive is written there directly,
              nothing touches the filesystem.
        """
        try:
            if isinstance(destination, (str, Path)):
                resolved_path = verify_destination(destination, self.path.name)
                buffer = io.BytesIO()
                self.package_into_buffer(buffer=buffer, sort_by_role=sort_by_role)
                resolved_path.write_bytes(buffer.getvalue())
            else:
                self.package_into_buffer(buffer=destination, sort_by_role=sort_by_role)
        except Exception as e:
            logger.error(f"package_into: failed to compress into EPUB: {e}")
            raise e

    def package_into_buffer(
        self,
        buffer: BinaryIO,
        sort_by_role: bool = True,
    ) -> None:
        resources = self.resources.iter(sort_by_role=sort_by_role)
        if self._package is not None:
            self._package.flush()
        with EpubZipSink(buffer) as sink:
            for resource in resources:
                sink.write_resource(resource)

    @contextmanager
    def keep_open(self) -> Generator[Self, None, None]:
        with self.source.open():
            yield self

    @contextmanager
    def stream_to(self, destination: str | Path) -> Generator[Self, None, None]:
        try:
            with self.source.open():
                yield self
        except EpubError:
            logger.error(f"{self} will not be packaged to {destination!r}.")
        else:
            self.package_into(destination)

    def info(self, read_data: bool = True):
        if self._info is None:
            with self.keep_open():
                total = self.resources.stats()
                images = self.resources.by_role(EpubRole.IMAGE).stats()
                htmls = self.resources.by_role(EpubRole.HTML).stats()
                fonts = self.resources.by_role(EpubRole.FONT).stats()

                if read_data:
                    package = self.package.document
                    identifier = package.metadata.uuid_id_or_all_identifiers
                    title = package.metadata.title
                    author = package.metadata.aut_or_all_creators
                else:
                    identifier = None
                    title = None
                    author = None

                self._info = EpubInfo(
                    path=self.path,
                    path_size=self.path.stat().st_size,
                    total=total,
                    images=images,
                    htmls=htmls,
                    fonts=fonts,
                    identifier=identifier,
                    title=title,
                    author=author,
                )

        return self._info


@dataclass(kw_only=True)
class EpubInfo:
    path: Path
    path_size: int
    total: IndexInfo | None = None
    images: IndexInfo | None = None
    htmls: IndexInfo | None = None
    fonts: IndexInfo | None = None
    identifier: str | None = None
    title: str | None = None
    author: str | None = None

    @classmethod
    def from_path(cls, path: Path) -> EpubInfo:
        """Read filesystem size only, without opening or parsing the EPUB."""
        return cls(path=path, path_size=path.stat().st_size)
