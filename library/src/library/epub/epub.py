import logging
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from os import PathLike
from pathlib import Path
from typing import Protocol, Self
from zipfile import ZipInfo, is_zipfile, ZipFile, Path as ZipPath

logger = logging.getLogger(__name__)


class EPUB:
    def __init__(self, path: str | PathLike) -> None:
        self.path = Path(path)


class SourceType(Enum):
    DIRECTORY = 0
    ZIPFILE = 1

class SourceProtocol(Protocol):
    def pathlist(self) -> list[PathLike]: ...
    def namelist(self) -> list[str]: ...
    def file_pathlist(self) -> list[PathLike]: ...
    def file_namelist(self) -> list[str]: ...
    def infolist(self) -> list[ZipInfo]: ...

    def getinfo(self, path: str | PathLike) -> ZipInfo: ...
    def read_text(self, path: str | PathLike) -> str: ...
    def read_bytes(self, path: str | PathLike) -> bytes: ...

    @contextmanager
    def open(self) -> Generator[Self, None, None]: ...





class SourceDirectory:
    """Read-only Directory source"""
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).absolute()
        self.log = logging.getLogger(self.__repr__())
        if not self.path.is_dir():
            raise NotADirectoryError(f"Path {path} is not a directory")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.path.name})"

    def _to_zipinfo(self, name: str) -> ZipInfo:
        return ZipInfo.from_file(
            self.path / name,
            arcname=name,
            strict_timestamps=False,
        )

    def _to_absolute_path(self, path: str | Path) -> Path:
        return self.path / path

    def _to_relative_path(self, path: str | Path) -> str:
        return self._to_absolute_path(path).relative_to(self.path).as_posix()

    def infolist(self) -> list[ZipInfo]:
        return [self._to_zipinfo(str(self._to_relative_path(file))) for file in self.path.rglob("*")]

    def getinfo(self, path: str | Path) -> ZipInfo:
        return self._to_zipinfo(str(self._to_relative_path(path)))

    def read_text(self, path: str | PathLike) -> str:
        return self._to_absolute_path(path).read_text()

    def read_bytes(self, path: str | PathLike) -> bytes:
        return self._to_absolute_path(path).read_bytes()

    def pathlist(self) -> list[Path]:
        return list(self.path.rglob("*"))

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


class SourceZipFile:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).absolute()
        self.log = logging.getLogger(self.__repr__())
        self.zip_file: ZipFile | None = None
        if not is_zipfile(path):
            raise ValueError("Path is not a ZipFile")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.path.name})"

    def infolist(self) -> list[ZipInfo]:
        with self.open():
            return self.zip_file.infolist()

    def getinfo(self, path: str | PathLike) -> ZipInfo:
        with self.open():
            return self.zip_file.getinfo(path)

    def read_bytes(self, path: str | PathLike) -> bytes:
        with self.open():
            return self.zip_file.read(path)

    def read_text(self, path: str | PathLike, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding)

    def pathlist(self) -> list[Path]:
        self.should_be_open()
        return list(ZipPath(self.zip_file).iterdir())

    def namelist(self) -> list[str]:
        with self.open():
            return self.zip_file.namelist()

    def file_pathlist(self) -> list[Path]:
        self.should_be_open()
        return [file for file in ZipPath(self.zip_file).iterdir() if file.is_file()]

    def file_namelist(self) -> list[str]:
        return [name for name in self.namelist() if not name.endswith("/")]


    @contextmanager
    def open(self) -> Generator[Self, None, None]:
        if self.zip_file is None:
            with ZipFile(self.path) as zip_file:
                self.log.debug(f"opening {self}")
                self.zip_file = zip_file
                yield self
                self.log.debug(f"closing {self}")
                self.zip_file = None
        else:
            yield self

    def should_be_open(self):
        if self.zip_file is None:
            self.log.error("This operation requires source to be open.")
            raise FileNotFoundError("This operation requires source to be open.")



