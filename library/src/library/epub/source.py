import logging
import shutil

from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, Self, Iterator, BinaryIO
from zipfile import ZipInfo, ZipFile, Path as ZipPath, is_zipfile

from library.asserts import require
from library.epub.utils_zip import apply_zipinfo_timestamp_to_file
from library.utils import ignore_absolute_paths

logger = logging.getLogger("source")


def _is_a_directory(path: str | ZipInfo | Path | ZipPath) -> bool:
    if isinstance(path, str):
        path = Path(path)
    assert isinstance(path, (ZipPath, Path, ZipInfo)), f"path is not of correct type ({type(path)})"
    return path.is_dir()


class SourceProtocol(Protocol):
    def getinfo(self, path: str | Path | ZipPath) -> ZipInfo | None: ...
    def getpath(self, path: str | Path | ZipPath) -> Path | ZipPath: ...

    def infolist(self) -> list[ZipInfo]: ...
    def pathlist(self) -> list[Path | ZipPath]: ...
    def namelist(self) -> list[str]: ...

    def read_text(self, path: str | ZipInfo | Path | ZipPath) -> str: ...
    def read_bytes(self, path: str | ZipInfo | Path | ZipPath) -> bytes: ...
    def write_to_zipfile(
        self, zip_file: ZipFile, path: str | Path | ZipInfo, compress_type: int | None = None
    ) -> None: ...

    @contextmanager
    def open(self) -> Iterator[Self]: ...

    @contextmanager
    def open_stream(self, path: str | ZipInfo | Path | ZipPath) -> Iterator[BinaryIO]: ...

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str: ...
    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None: ...


class DirectorySource(SourceProtocol):
    """Read-only Directory source"""

    def __init__(self, path: str | Path, skip_dirs: bool = False) -> None:
        self.root = Path(path).absolute()
        self.skip_dirs = skip_dirs
        if not self.root.is_dir():
            raise NotADirectoryError(f"Path {path} is not a directory")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.root.name!r})"

    def _to_zipinfo(self, name: str) -> ZipInfo | None:
        if not (self.root / name).exists():
            return None
        return ZipInfo.from_file(self.root / name, arcname=name, strict_timestamps=False)

    def _to_absolute_path(self, path: str | ZipInfo | Path) -> Path:
        if isinstance(path, ZipInfo):
            return self.root / path.filename
        return self.root / path

    def _to_relative_path(self, path: str | ZipInfo | Path) -> str:
        if isinstance(path, ZipInfo):
            return path.filename
        return self._to_absolute_path(path).relative_to(self.root).as_posix()

    def getinfo(self, path: str | Path | ZipInfo) -> ZipInfo | None:
        if isinstance(path, ZipInfo):
            return path
        return self._to_zipinfo(self._to_relative_path(path))

    def infolist(self) -> list[ZipInfo]:
        if self.skip_dirs:
            return [self.getinfo(file) for file in self.root.rglob("*") if not file.is_dir()]
        return [self.getinfo(file) for file in self.root.rglob("*")]

    def getpath(self, path: str | Path | ZipPath) -> Path:
        return self._to_absolute_path(path)

    def pathlist(self) -> list[Path]:
        if self.skip_dirs:
            return [file for file in self.root.rglob("*") if not file.is_dir()]
        return list(self.root.rglob("*"))

    def namelist(self) -> list[str]:
        return [info.filename for info in self.infolist()]

    def read_bytes(self, path: str | ZipInfo | Path) -> bytes:
        logger.warning(f"{self} reading {path!r} bytes")
        return self._to_absolute_path(path).read_bytes()

    def read_text(self, path: str | ZipInfo | Path, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding=encoding)

    @contextmanager
    def open(self) -> Iterator[Self]:
        logger.debug(f"{self} opening")
        yield self
        logger.debug(f"{self} closing")

    @contextmanager
    def open_stream(self, path: str | ZipInfo | Path) -> Iterator[BinaryIO]:
        if _is_a_directory(path):
            message = f"{self} Path {path!r} is a directory, cannot open stream"
            logger.error(message)
            raise IsADirectoryError(message)

        if isinstance(path, (str, ZipInfo)):
            path = self._to_absolute_path(path)
        assert isinstance(path, Path), f"path is not of correct type ({type(path)})"
        logger.debug(f"{self} streaming {path.name!r}")

        with path.open("rb") as stream:
            yield stream

    def write_to_zipfile(self, zip_file: ZipFile, path: str | Path | ZipInfo, compress_type: int | None = None) -> None:
        absolute_path = self._to_absolute_path(path)
        relative_path = self._to_relative_path(path)
        zip_file.write(filename=absolute_path, arcname=relative_path, compress_type=compress_type)

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str:
        logger.info(f"{self} extract({destination}, {member.filename if isinstance(member, ZipInfo) else member})")
        return shutil.copy2(src=self._to_absolute_path(member), dst=destination)

    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None:
        logger.info(f"{self} extract_all({repr(destination)}, {exclude_members=})")
        ignore = None
        if exclude_members is not None:
            exclude_members = [self._to_absolute_path(m) for m in exclude_members]
            ignore = ignore_absolute_paths(absolute_paths=exclude_members)
        shutil.copytree(src=self.root, dst=destination, dirs_exist_ok=True, ignore=ignore)


class ZipFileSource(SourceProtocol):
    def __init__(self, path: str | Path, skip_dirs: bool = False) -> None:
        self.root = Path(path).absolute()
        self.skip_dirs = skip_dirs
        self.zip_file: ZipFile | None = None
        if not is_zipfile(path):
            raise ValueError("Path is not a ZipFile")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.root.name!r})"

    def _should_be_open(self):
        if self.zip_file is None:
            logger.error(f"{self} This operation requires source to be open.")
            raise IOError("This operation requires source to be open.")

    def getinfo(self, path: str | ZipPath | ZipInfo) -> ZipInfo | None:
        if isinstance(path, ZipInfo):
            return path
        if isinstance(path, ZipPath):
            path = path.at
        with self.open():
            try:
                return self.zip_file.getinfo(str(path))
            except KeyError:
                return None

    def getpath(self, path: str | ZipPath | ZipInfo) -> ZipPath:
        self._should_be_open()
        info = require(self.getinfo(path))
        return ZipPath(root=require(self.zip_file), at=info.filename)

    def infolist(self) -> list[ZipInfo]:
        with self.open():
            if self.skip_dirs:
                return [info for info in self.zip_file.infolist() if not info.is_dir()]
            return self.zip_file.infolist()

    def pathlist(self) -> list[ZipPath]:
        self._should_be_open()
        # return list(set(ZipPath(self.zip_file).glob("*")) | set(ZipPath(self.root).rglob("*")))
        return [self.getpath(info) for info in self.infolist()]

    def namelist(self) -> list[str]:
        with self.open():
            if self.skip_dirs:
                return [info.filename for info in self.infolist()]
            return self.zip_file.namelist()

    def read_bytes(self, path: str | ZipInfo | ZipPath) -> bytes:
        if _is_a_directory(path):
            message = f"{self} Path {path!r} is a directory, cannot read bytes"
            logger.error(message)
            raise IsADirectoryError(message)
        if isinstance(path, ZipPath):
            logger.debug(f"{self} reading the {path.at!r} bytes")
            self._should_be_open()
            return path.read_bytes()
        with self.open():
            logger.debug(f"{self} reading the {(path if isinstance(path, str) else path.filename)!r} bytes")
            return self.zip_file.read(path)

    def read_text(self, path: str | ZipInfo | ZipPath, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding=encoding)

    @contextmanager
    def open(self) -> Iterator[Self]:
        if self.zip_file is None:
            with ZipFile(self.root) as zip_file:
                logger.debug(f"{self} opening")
                self.zip_file = zip_file
                yield self
                logger.debug(f"{self} closing")
                self.zip_file = None
        else:
            yield self

    @contextmanager
    def open_stream(self, path: str | ZipInfo | ZipPath) -> Iterator[BinaryIO]:
        if _is_a_directory(path):
            message = f"{self} Path {path!r} is a directory, cannot open stream"
            logger.error(message)
            raise IsADirectoryError(message)

        if isinstance(path, ZipPath):
            logger.debug(f"{self} streaming {path.at!r}")
            self._should_be_open()
            with path.open("rb") as stream:
                yield stream
        else:
            with self.open():
                filename = path if isinstance(path, str) else path.filename
                logger.debug(f"{self} streaming {filename!r}")

                with require(self.zip_file).open(path, "r") as stream:
                    yield stream

    def write_to_zipfile(self, zip_file: ZipFile, path: str | Path | ZipInfo, compress_type: int | None = None) -> None:
        zip_info = require(self.getinfo(path))
        if not zip_file.fp:
            raise ValueError("Attempt to write to ZIP archive that was already closed")
        if zip_file._writing:
            raise ValueError("Can't write to ZIP archive while an open writing handle exists")

        if zip_info.is_dir():
            logger.warning(f"{self} writing a directory to ZIP archive, this should not happen.")
            zip_info.compress_size = 0
            zip_info.CRC = 0
            zip_file.mkdir(zip_info)
        else:
            data_bytes = self.read_bytes(zip_info)
            zip_info.compress_type = compress_type if compress_type is not None else zip_file.compression
            zip_info.compress_level = zip_file.compresslevel

            with zip_file.open(zip_info, "w") as dest:
                dest.write(data_bytes)

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str:
        """Extract a single element from source.

        Args:
            destination: destination filename (str | Path) or destination directory (must exist) (Path).
            member: member to extract to (str | ZipInfo).
        """
        destination: Path = Path(destination)
        with self.open():
            info = member if isinstance(member, ZipInfo) else require(self.getinfo(member))
            if destination.is_dir():
                destination = destination / info.filename
            logger.info(f"{self} extract({destination!r}, {info.filename!r})")
            result = self.zip_file.extract(member=info, path=destination)
            apply_zipinfo_timestamp_to_file(info, destination)  # preserving mtime

            return result

    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None:
        """Extract all data from source.

        Args:
            destination: destination directory (must exist) (Path).
            exclude_members: member to not extract.
        """
        logger.info(f"{self} extract_all({destination!r}, {exclude_members=})")
        destination: Path = Path(destination)
        assert destination.is_dir(), "destination must be a directory"

        with self.open():
            members = self.infolist()
            if exclude_members is not None:
                exclude_members = [m if isinstance(m, str) else m.filename for m in exclude_members]
                members = [info for info in members if info.filename not in exclude_members]

            self.zip_file.extractall(path=destination, members=members)

            for file_zip_info in members:
                full_path = destination / file_zip_info.filename
                apply_zipinfo_timestamp_to_file(file_zip_info, full_path)  # preserving mtime
