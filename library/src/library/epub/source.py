import logging
import shutil

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Protocol, Self
from zipfile import ZipInfo, ZipFile, Path as ZipPath, is_zipfile


def _is_a_directory(path: str | ZipInfo | Path | ZipPath) -> bool:
    if isinstance(path, (ZipPath, Path, ZipInfo)):
        return path.is_dir()
    if isinstance(path, str):
        return Path(path).is_dir()
    raise NotImplementedError(f"Path {path} of type {type(path)} is not supported")


class SourceType(Enum):
    DIRECTORY = 0
    ZIPFILE = 1


class SourceProtocol(Protocol):
    def pathlist(self) -> list[Path | ZipPath]: ...
    def namelist(self) -> list[str]: ...
    def file_pathlist(self) -> list[Path | ZipPath]: ...
    def file_namelist(self) -> list[str]: ...
    def infolist(self) -> list[ZipInfo]: ...

    def getinfo(self, path: str | Path | ZipPath) -> ZipInfo: ...
    def read_text(self, path: str | ZipInfo | Path | ZipPath) -> str: ...
    def read_bytes(self, path: str | ZipInfo | Path | ZipPath) -> bytes: ...

    @contextmanager
    def open(self) -> Generator[Self, None, None]: ...

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str: ...
    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None: ...


class DirectorySource:
    """Read-only Directory source"""

    def __init__(self, path: str | Path) -> None:
        self.root = Path(path).absolute()
        self.log = logging.getLogger(self.__repr__())
        if not self.root.is_dir():
            raise NotADirectoryError(f"Path {path} is not a directory")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.root.name})"

    def _to_zipinfo(self, name: str) -> ZipInfo:
        return ZipInfo.from_file(
            self.root / name,
            arcname=name,
            strict_timestamps=False,
        )

    def _to_absolute_path(self, path: str | ZipInfo | Path) -> Path:
        if isinstance(path, ZipInfo):
            return self.root / path.filename
        return self.root / path

    def _to_relative_path(self, path: str | ZipInfo | Path) -> str:
        if isinstance(path, ZipInfo):
            return path.filename
        return self._to_absolute_path(path).relative_to(self.root).as_posix()

    def infolist(self) -> list[ZipInfo]:
        return [self.getinfo(file) for file in self.root.rglob("*")]

    def getinfo(self, path: str | Path) -> ZipInfo:
        return self._to_zipinfo(str(self._to_relative_path(path)))

    def read_bytes(self, path: str | ZipInfo | Path) -> bytes:
        self.log.warning(f"reading {path} bytes")
        return self._to_absolute_path(path).read_bytes()

    def read_text(self, path: str | ZipInfo | Path, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding=encoding)

    def pathlist(self) -> list[Path]:
        return list(self.root.rglob("*"))

    def namelist(self) -> list[str]:
        return [info.filename for info in self.infolist()]

    def file_pathlist(self) -> list[Path]:
        return [p for p in self.pathlist() if p.is_file()]

    def file_namelist(self) -> list[str]:
        return [info.filename for info in self.infolist() if not info.is_dir()]

    @contextmanager
    def open(self):
        self.log.debug(f"opening {self}")
        yield self
        self.log.debug(f"closing {self}")

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str:
        return shutil.copy2(src=self._to_absolute_path(member), dst=destination)

    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None:
        ignore = None
        if exclude_members is not None:
            ignore = shutil.ignore_patterns(*exclude_members)
        shutil.copytree(src=self.root, dst=destination, dirs_exist_ok=True, ignore=ignore)


class ZipFileSource:
    def __init__(self, path: str | Path) -> None:
        self.root = Path(path).absolute()
        self.log = logging.getLogger(self.__repr__())
        self.zip_file: ZipFile | None = None
        if not is_zipfile(path):
            raise ValueError("Path is not a ZipFile")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.root.name})"

    def infolist(self) -> list[ZipInfo]:
        with self.open():
            return self.zip_file.infolist()

    def getinfo(self, path: str | ZipPath) -> ZipInfo:
        with self.open():
            return self.zip_file.getinfo(path)

    def read_bytes(self, path: str | ZipInfo | ZipPath) -> bytes:
        self.log.warning(f"reading the {path} bytes")
        if _is_a_directory(path):
            self.log.error(f"Path {path} is a directory, cannot read bytes")
            raise IsADirectoryError(f"Path {path} is a directory, cannot read bytes")
        if isinstance(path, ZipPath):
            self._should_be_open()
            return path.read_bytes()
        with self.open():
            return self.zip_file.read(path)

    def read_text(self, path: str | ZipInfo | ZipPath, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding=encoding)

    def pathlist(self) -> list[Path]:
        self._should_be_open()
        return list(set(ZipPath(self.zip_file).glob("*")) | set(ZipPath(self.root).rglob("*")))

    def namelist(self) -> list[str]:
        with self.open():
            return self.zip_file.namelist()

    def file_pathlist(self) -> list[Path]:
        self._should_be_open()
        return [file for file in self.pathlist() if file.is_file()]

    def file_namelist(self) -> list[str]:
        return [name for name in self.namelist() if not name.endswith("/")]

    @contextmanager
    def open(self) -> Generator[Self, None, None]:
        if self.zip_file is None:
            with ZipFile(self.root) as zip_file:
                self.log.debug(f"opening {self}")
                self.zip_file = zip_file
                yield self
                self.log.debug(f"closing {self}")
                self.zip_file = None
        else:
            yield self

    def _should_be_open(self):
        if self.zip_file is None:
            self.log.error("This operation requires source to be open.")
            raise IOError("This operation requires source to be open.")

    def extract(self, destination: str | Path, member: str | ZipInfo) -> str:
        with self.open():
            return self.zip_file.extract(member=member, path=destination)

    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None:
        with self.open():
            members = None
            if exclude_members is not None:
                members = [m for m in self.namelist() if m not in exclude_members]
            self.zip_file.extractall(path=destination, members=members)
