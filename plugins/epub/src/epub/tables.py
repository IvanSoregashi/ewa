from collections.abc import Iterable
from datetime import datetime
from typing import Any, Self, Generator
from pathlib import Path
from zipfile import ZipInfo

from sqlmodel import SQLModel, Field
from epub.utils import ts_to_dt, bt_to_mb
from ewa.ui import print_error


class EpubFileData(SQLModel, table=True):
    filepath: str = Field(primary_key=True, index=True)
    filesize: int
    mtime: float
    ctime: float
    hash: str | None = None
    toc_hash: str | None = None

    @classmethod
    def from_path(cls, path: Path):
        filepath = str(path.absolute())
        stat = path.stat()
        filesize = stat.st_size
        mtime = stat.st_mtime
        ctime = stat.st_ctime
        return cls(filepath=filepath, filesize=filesize, mtime=mtime, ctime=ctime)

    @classmethod
    def try_to_convert_iterable(
        cls, iterable: Iterable[Any]
    ) -> Generator[Self, None, None]:
        iterator = iter(iterable)
        first_item = next(iterator)
        if isinstance(first_item, cls):
            return iterable
        if not isinstance(first_item, Path):
            raise TypeError(
                f"Can not convert item of type {type(first_item)} to {cls.__name__}"
            )
        yield cls.from_path(first_item)
        yield from map(cls.from_path, iterator)

    def as_dict(self) -> dict[str, Any]:
        result = {}
        result["filepath"] = str(self.filepath)
        result["filesize"] = bt_to_mb(self.filesize)
        result["ctime"] = ts_to_dt(self.ctime)
        result["mtime"] = ts_to_dt(self.mtime)
        return result

    def as_list(self):
        return list(self.as_dict().values())


class EpubContentData(SQLModel, table=True):
    epub_filepath: str = Field(primary_key=True)
    opf_hash: str = Field(default=None)
    filepath: str = Field(primary_key=True, index=True)
    filename: str
    suffix: str
    filesize: int
    compressed_size: int
    timestamp: float

    @classmethod
    def from_zip_info(cls, epub_filename: Path, zip_info: ZipInfo):
        zip_path = Path(zip_info.filename)
        try:
            timestamp = datetime(*zip_info.date_time).timestamp()
        except Exception as e:
            print_error(f"Error parsing date_time {zip_info.date_time}: {e}")
            timestamp = 0
        return cls(
            epub_filepath=str(epub_filename),
            filepath=zip_info.filename,
            filename=zip_path.stem,
            suffix=zip_path.suffix,
            filesize=zip_info.file_size,
            compressed_size=zip_info.compress_size,
            timestamp=timestamp,
        )
