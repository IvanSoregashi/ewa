import logging
import os
import shutil

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Protocol, Self
from zipfile import ZipInfo, ZipFile, Path as ZipPath, is_zipfile

from library.epub.zip_utils import zipinfo_to_timestamp
from library.utils import ignore_absolute_paths


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

    def getpath(self, path: str | Path | ZipPath) -> Path | ZipPath: ...
    def getinfo(self, path: str | Path | ZipPath) -> ZipInfo: ...
    def read_text(self, path: str | ZipInfo | Path | ZipPath) -> str: ...
    def read_bytes(self, path: str | ZipInfo | Path | ZipPath) -> bytes: ...
    def write_to_zipfile(self, zip_file: ZipFile, path: str | Path | ZipInfo, compress_type: int | None = None) -> None: ...

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

    def getpath(self, path: str | Path | ZipPath) -> Path:
        return self._to_absolute_path(path)

    def getinfo(self, path: str | Path | ZipInfo) -> ZipInfo:
        if isinstance(path, ZipInfo):
            return path
        return self._to_zipinfo(self._to_relative_path(path))

    def read_bytes(self, path: str | ZipInfo | Path) -> bytes:
        self.log.warning(f"reading {path} bytes")
        return self._to_absolute_path(path).read_bytes()

    def read_text(self, path: str | ZipInfo | Path, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding=encoding)

    def write_to_zipfile(self, zip_file: ZipFile, path: str | Path | ZipInfo, compress_type: int | None = None) -> None:
        absolute_path = self._to_absolute_path(path)
        relative_path = self._to_relative_path(path)
        zip_file.write(filename=absolute_path, arcname=relative_path, compress_type=compress_type)

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
        self.log.info(f"{self}.extract({destination}, {member.filename if isinstance(member, ZipInfo) else member})")
        return shutil.copy2(src=self._to_absolute_path(member), dst=destination)

    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None:
        self.log.info(f"{self}.extract_all({repr(destination)}, {exclude_members=})")
        ignore = None
        if exclude_members is not None:
            exclude_members = [self._to_absolute_path(m) for m in exclude_members]
            ignore = ignore_absolute_paths(absolute_paths=exclude_members)
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

    def getinfo(self, path: str | ZipPath | ZipInfo) -> ZipInfo:
        if isinstance(path, ZipInfo):
            return path
        if isinstance(path, ZipPath):
            path = path.at
        with self.open():
            return self.zip_file.getinfo(str(path))

    def getpath(self, path: str | ZipPath | ZipInfo) -> ZipPath:
        self._should_be_open()
        info = self.getinfo(path)
        return ZipPath(root=self.zip_file, at=info.filename)

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

    def write_to_zipfile(self, zip_file: ZipFile, path: str | Path | ZipInfo, compress_type: int | None = None) -> None:
        zip_info = self.getinfo(path)
        if not zip_file.fp:
            raise ValueError("Attempt to write to ZIP archive that was already closed")
        if zip_file._writing:
            raise ValueError("Can't write to ZIP archive while an open writing handle exists")

        if zip_info.is_dir():
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
        with self.open():
            member = member if isinstance(member, ZipInfo) else self.getinfo(member)
            self.log.info(f"{self}.extract({destination}, {member.filename})")
            result = self.zip_file.extract(member=member, path=destination)

            # When using extractall (or extract) file's mtime is not preserved
            full_path = destination / member.filename
            timestamp = zipinfo_to_timestamp(member)
            os.utime(full_path, times=(timestamp, timestamp))

            return result

    def extract_all(self, destination: str | Path, exclude_members: Iterable[str | ZipInfo] | None = None) -> None:
        self.log.info(f"{self}.extract_all({repr(destination)}, {exclude_members=})")
        destination = Path(destination)
        with self.open():
            members = self.infolist()
            if exclude_members is not None:
                exclude_members = [m if isinstance(m, str) else m.filename for m in exclude_members]
                members = [info for info in members if info.filename not in exclude_members]

            self.zip_file.extractall(path=destination, members=members)

            # When using extractall (or extract) file's mtime is not preserved
            for file_zip_info in members:
                full_path = destination / file_zip_info.filename
                timestamp = zipinfo_to_timestamp(file_zip_info)
                os.utime(full_path, times=(timestamp, timestamp))  # Set the access and modification times
