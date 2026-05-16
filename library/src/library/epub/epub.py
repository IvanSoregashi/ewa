import logging
import tempfile
from collections.abc import Generator, Iterable, Container
from contextlib import contextmanager
from pathlib import Path
from typing import Self
from zipfile import is_zipfile, ZipFile, ZIP_STORED, ZIP_DEFLATED, ZipInfo

from library.asserts import require
from library.epub.epub_core import EpubCore, EpubSpecification
from library.epub.resources import EPUBResource
from library.epub.resource_index import ResourceIndex
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol
from library.epub.xml_literals import FileContents
from library.epub.media_type import FileName

logger = logging.getLogger("epub")


class EpubError(Exception): ...


class EpubSpecificationError(EpubError): ...


class EPUB:
    def __init__(self, path: str | Path) -> None:
        """Initialize an EPUB object with path to epub file or a directory."""
        self.path: Path = Path(path)
        self.__skip_dirs: bool = True
        self.__confirmed_epub: bool = False

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

    def is_specification(self, specification: EpubSpecification):
        match specification:
            case EpubSpecification.SERENE_PANDA_ENCRYPTED:
                strict_font = self.source.getinfo(FileName.SP_FONT)
                return strict_font is not None
            case _:
                raise ValueError(f"Specification {specification} is not Implemented")

    def require_specification(self, specification: EpubSpecification):
        if not self.is_specification(specification):
            message = f"{self} does not adhere to specification {specification.value!r}"
            logger.error(message)
            raise EpubSpecificationError(message)

    def scan_resources(self) -> ResourceIndex:
        """Scan the EPUB source and build a ResourceIndex from all files."""
        logger.debug("scanning EPUB resources")
        with self.source.open():
            resources = [EPUBResource(info, self.source.read_bytes) for info in self.source.infolist()]
        return ResourceIndex(resources)

    @property
    def resources(self) -> ResourceIndex:
        """Lazily initialize and return the ResourceIndex for this EPUB."""
        if self._resources is None:
            self.confirm_mimetype()
            self._resources: ResourceIndex = self.scan_resources()
        assert self._resources is not None, f"{self} resource_index could not be initialized."
        return self._resources

    @property
    def core(self) -> EpubCore:
        """Lazily initialize and return the EpubCore for this EPUB."""
        if self._core is None:
            self._core: EpubCore = EpubCore(self.resources)
        assert self._core is not None, f"{self} epub_core could not be initialized."
        return self._core

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
        destination: str | Path,
        exclude_members: Iterable[str | ZipInfo] | None = None,
        validity_check: bool = True,
    ):
        """

        Args:
            destination: either non-existing path to epub, or path to existing directory.
            exclude_members: list of files to exclude from packaging.
            validity_check: minimal confirmation of epub's validity before archiving.
        """
        if validity_check:
            self.confirm_mimetype()

        destination: Path = Path(destination)
        # destination ensure path file
        if destination.suffix.lower() != ".epub":
            if destination.is_dir():
                destination = destination / self.path.name
            else:
                raise NotADirectoryError(f"Path {destination} is neither a directory nor a epub.")

        # destination ensure file path is available
        if destination.suffix.lower() == ".epub":
            if destination.exists():
                raise FileExistsError(f"File {destination} already exists.")
            if not destination.parent.exists():
                # TODO Create folder?
                raise FileNotFoundError(f"Directory {destination.parent} does not exist.")

        if self._core is not None:
            self._core.sync()

        # exclude_members
        exclude = {m if isinstance(m, ZipInfo) else require(self.source.getinfo(m)) for m in (exclude_members or [])}

        try:
            if self._core is not None:
                self._package_from_core(destination=destination, exclude_members=exclude)
            elif self._resources is not None:
                self._package_from_infolist(destination=destination, exclude_members=exclude)
            else:
                self._package_from_resource_list(destination=destination, exclude_members=exclude)
        except Exception as e:
            logger.error(f"package_into: failed to compress into EPUB: {e}")
            raise e
        logger.info(f"{self} successfully packaged into EPUB({destination}).")

    def _package_from_infolist(self, destination: Path, exclude_members: Container[ZipInfo]):
        with self.source.open(), ZipFile(destination, "w", compression=ZIP_DEFLATED) as zipf:
            mimetype_info = require(self.source.getinfo(FileName.MIMETYPE))
            # TODO: CAN SAVE READS HERE, JUST WRITE THE DEAFULT DATA
            self.source.write_to_zipfile(zipf, mimetype_info, compress_type=ZIP_STORED)

            for zip_info in self.source.infolist():
                if zip_info in exclude_members:
                    continue
                if zip_info.filename == FileName.MIMETYPE:
                    continue
                if self.__skip_dirs and zip_info.is_dir():
                    continue
                self.source.write_to_zipfile(zipf, zip_info)

    def _package_from_resource_list(self, destination: Path, exclude_members: Container[ZipInfo]):
        with self.source.open(), ZipFile(destination, "w", compression=ZIP_DEFLATED) as zipf:
            mimetype_info = require(self.source.getinfo(FileName.MIMETYPE))
            # TODO: CAN SAVE READS HERE, JUST WRITE THE DEAFULT DATA
            self.source.write_to_zipfile(zipf, mimetype_info, compress_type=ZIP_STORED)

            for resource in self.resources:
                if resource.info in exclude_members:
                    continue
                if self.__skip_dirs and resource.info.is_dir():
                    continue
                if resource.filename == FileName.MIMETYPE:
                    continue
                if resource.is_deleted:
                    continue

                if resource.is_modified:
                    logger.debug(f"Writing modified {resource}.")
                    zip_info = resource.null_info
                    # TODO is there data that needs to be modified?
                    # Write bytes from memory
                    zipf.writestr(zip_info, resource.content)
                else:
                    logger.debug(f"Writing original {resource}.")
                    # Stream untouched bytes from source
                    self.source.write_to_zipfile(zipf, resource.info)

    def _package_from_core(self, destination: Path, exclude_members: Container[ZipInfo]):
        with self.source.open(), ZipFile(destination, "w", compression=ZIP_DEFLATED) as zipf:
            mimetype_info = require(self.source.getinfo(FileName.MIMETYPE))
            # TODO: CAN SAVE READS HERE, JUST WRITE THE DEAFULT DATA
            self.source.write_to_zipfile(zipf, mimetype_info, compress_type=ZIP_STORED)

            for resource in self.core.writing_sequence():
                if resource.info in exclude_members:
                    continue
                if self.__skip_dirs and resource.info.is_dir():
                    continue

                if resource.is_modified:
                    logger.debug(f"Writing modified {resource}.")
                    zip_info = resource.null_info
                    # Write bytes from memory
                    zipf.writestr(zip_info, resource.content)
                else:
                    logger.debug(f"Writing original {resource}.")
                    # Stream untouched bytes from source
                    self.source.write_to_zipfile(zipf, resource.info)

    @contextmanager
    def stream_to(self, destination: str | Path) -> Generator[Self, None, None]:
        try:
            with self.source.open():
                yield self
        except EpubError:
            logger.error(f"{self} will not be packaged to {destination!r}.")
        else:
            self.package_into(destination)

    def save_changes_to_a_dir(self, directory: Path):
        for resource in self.resources:
            if resource.is_deleted:
                logger.info(f"{resource} has been deleted.")
                continue
            if resource.is_modified:
                filepath = directory / resource.filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                resource.write_to_filesystem(filepath)
