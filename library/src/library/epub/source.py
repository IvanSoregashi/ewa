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

def _ensure_not_a_directory(path: str | ZipInfo | Path | ZipPath, message:str=""):
    if _is_a_directory(path):
        message = f"Path {path!r} is a directory: {message}"
        logger.error(message)
        raise IsADirectoryError(message)


class SourceProtocol(Protocol):
    def getinfo(self, path: str | Path | ZipPath) -> ZipInfo | None: ...
    def getpath(self, path: str | Path | ZipPath) -> Path | ZipPath: ...

    def infolist(self) -> list[ZipInfo]: ...
    def pathlist(self) -> list[Path | ZipPath]: ...
    def namelist(self) -> list[str]: ...

    def read_text(self, path: str | ZipInfo | Path | ZipPath) -> str: ...
    def read_bytes(self, path: str | ZipInfo | Path | ZipPath) -> bytes: ...

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

    def _require_file_path(self, path: str | ZipInfo | Path):
        filepath = self._to_absolute_path(path)
        if not filepath.exists():
            raise FileNotFoundError(f"{self} Path {path!r} does not exist")
        if filepath.is_dir():
            raise IsADirectoryError(f"{self} Path {path!r} is a directory")
        return filepath

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
        return self._require_file_path(path).read_bytes()

    def read_text(self, path: str | ZipInfo | Path, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding=encoding)

    @contextmanager
    def open(self) -> Iterator[Self]:
        logger.debug(f"{self} opening")
        yield self
        logger.debug(f"{self} closing")

    @contextmanager
    def open_stream(self, path: str | ZipInfo | Path) -> Iterator[BinaryIO]:
        filepath = self._require_file_path(path)
        with filepath.open("rb") as stream:
            yield stream

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str:
        filepath = self._require_file_path(member)
        logger.debug(f"{self} extract({destination}, {filepath})")
        return shutil.copy2(src=filepath, dst=str(destination))

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
        self._zip_file: ZipFile | None = None
        if not is_zipfile(path):
            raise ValueError("Path is not a ZipFile")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.root.name!r})"

    @property
    def zip_file(self) -> ZipFile:
        return require(self._zip_file, f"{self}._zip_file")

    def _require_file_info(self, path: str | ZipPath | ZipInfo) -> ZipInfo:
        info: ZipInfo = require(self.getinfo(path), f"{self}.getinfo({path!r})")
        if info.is_dir():
            message = f"{self} Path {path!r} is a directory"
            logger.error(message)
            raise IsADirectoryError(message)
        return info

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
        info = require(self.getinfo(path))
        return ZipPath(root=self.zip_file, at=info.filename)

    def infolist(self) -> list[ZipInfo]:
        with self.open():
            if self.skip_dirs:
                return [info for info in self.zip_file.infolist() if not info.is_dir()]
            return self.zip_file.infolist()

    def pathlist(self) -> list[ZipPath]:
        # return list(set(ZipPath(self.zip_file).glob("*")) | set(ZipPath(self.root).rglob("*")))
        return [self.getpath(info) for info in self.infolist()]

    def namelist(self) -> list[str]:
        with self.open():
            if self.skip_dirs:
                return [info.filename for info in self.infolist()]
            return self.zip_file.namelist()

    def read_bytes(self, path: str | ZipInfo | ZipPath) -> bytes:
        with self.open():
            info = self._require_file_info(path)
            return self.zip_file.read(info)

    def read_text(self, path: str | ZipInfo | ZipPath, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding=encoding)

    @contextmanager
    def open(self) -> Iterator[Self]:
        if self._zip_file is None:
            with ZipFile(self.root) as zip_file:
                logger.debug(f"{self} opening")
                self._zip_file = zip_file
                yield self
                logger.debug(f"{self} closing")
                self._zip_file = None
        else:
            yield self

    @contextmanager
    def open_stream(self, path: str | ZipInfo | ZipPath) -> Iterator[BinaryIO]:
        with self.open():
            info = self._require_file_info(path)
            with self.zip_file.open(info, "r") as stream:
                yield stream

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str:
        """Extract a single element from source.

        Args:
            destination: destination filename (str | Path) or destination directory (must exist) (Path).
            member: member to extract to (str | ZipInfo).
        """
        destination: Path = Path(destination)
        with self.open():
            info = require(self.getinfo(member), f"{self}.getinfo({member!r})")
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
        logger.info(f"{self}.extract_all({destination!r}, {exclude_members=})")
        destination: Path = Path(destination)
        if not destination.exists():
            destination.mkdir(parents=True)
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
