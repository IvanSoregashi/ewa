import io
import logging
from collections.abc import Generator, Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Self
from zipfile import is_zipfile

from library.asserts import require
from library.epub.epub_core import EpubCore
from library.epub.errors import EpubSpecificationError, EpubError
from library.epub.media_type import EpubRole
from library.epub.resources import ResourceIndex
from library.epub.sink import EpubZipSink
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol

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

    def package_into(
        self,
        destination: str | Path | io.BytesIO,
        manifest_only: bool = False,
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
        buffer = destination if isinstance(destination, io.BytesIO) else io.BytesIO()
        self.package_into_buffer(buffer=buffer, manifest_only=manifest_only, sort_by_role=sort_by_role)
        if isinstance(destination, (str, Path)):
            try:
                resolved_path = self._verify_destination(destination)
                resolved_path.write_bytes(buffer.getvalue())
            except Exception as e:
                logger.error(f"package_into: failed to compress into EPUB: {e}")
                raise e

    def package_into_buffer(
        self,
        buffer: BinaryIO,
        manifest_only: bool = False,
        sort_by_role: bool = True,
    ) -> None:
        resources = self.get_resources(manifest_only=manifest_only).iter(sort_by_role=sort_by_role)
        with EpubZipSink(buffer) as sink:
            for resource in resources:
                sink.write_resource(resource)

    def _verify_destination(self, destination: str | Path) -> Path:
        destination: Path = Path(destination)
        if destination.suffix.lower() != ".epub":
            if not destination.is_dir():
                raise NotADirectoryError(f"Path {destination} is neither a directory nor a epub.")
            destination = destination / self.path.name
        if destination.exists():
            raise FileExistsError(f"File {destination} already exists.")
        if not destination.parent.exists():
            destination.parent.mkdir(parents=True)
        return destination

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

    def info(self):
        with self.keep_open():
            images = self.resources.by_role(EpubRole.IMAGE)
            package = self.core.package
            return EpubInfo(
                path=self.path,
                file_size=self.path.stat().st_size,
                file_count=len(self.resources),
                images_size=sum(image.info.file_size for image in images),
                images_count=len(images),
                chapters=len(package.spine.itemrefs),
                identifier=package.metadata.uuid_id_or_all_identifiers,
                title=package.metadata.title,
                author=package.metadata.aut_or_all_creators,
            )


@dataclass(kw_only=True)
class EpubInfo:
    path: Path
    file_size: int
    file_count: int | None
    images_size: int | None
    images_count: int | None
    chapters: int | None
    identifier: str | None
    title: str | None
    author: str | None

    @classmethod
    def failed(cls, path: Path) -> EpubInfo:
        return cls(path=path, file_size=path.stat().st_size)
