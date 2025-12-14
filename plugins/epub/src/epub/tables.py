from hashlib import md5
from typing import Any
from pathlib import Path
from zipfile import ZipInfo

from bs4 import BeautifulSoup
from sqlmodel import SQLModel, Field, Relationship
from epub.utils import timestamp_from_zip_info, string_to_int_hash
from ewa.sqlite_model_table import SQLiteModelTable


class EpubBookModel(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    filepath: str = Field(index=True)
    filesize: int
    mtime: int
    ctime: int

    opf_hash: str | None = None
    title: str | None = None
    creator: str | None = None

    contents: list[EpubContentsModel] = Relationship(back_populates="book")

    @classmethod
    def from_path(cls, path: Path) -> EpubBookModel:
        stat = path.stat()
        return cls(
            id=string_to_int_hash(str(path)),
            filepath=str(path.absolute()),
            filesize=stat.st_size,
            mtime=int(stat.st_mtime),
            ctime=int(stat.st_ctime),
        )

    def update_from_opf_file(self, opf_bytes: bytes) -> None:
        self.opf_hash = md5(opf_bytes).hexdigest()
        soup = BeautifulSoup(opf_bytes, "xml")
        metadata = soup.find("metadata")
        if metadata:
            title = metadata.find("dc:title")
            self.title = title and title.text
            creator = metadata.find("dc:creator")
            self.creator = creator and creator.text

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()  # TODO: proper formatting

    def as_list(self) -> list:
        return list(map(str, self.as_dict().values()))  # TODO: proper formatting

    def as_epub(self): ...


class EpubContentsModel(SQLModel, table=True):
    book_id: int = Field(primary_key=True, foreign_key="epubbookmodel.id")
    filepath: str = Field(primary_key=True)
    filesize: int
    compressed_size: int
    timestamp: int

    book: EpubBookModel = Relationship(back_populates="contents")

    @staticmethod
    def dict_from_zip_info(zip_info: ZipInfo, book_id: int) -> dict[str, Any]:
        return {
            "book_id": book_id,
            "filepath": zip_info.filename,
            "filesize": zip_info.file_size,
            "compressed_size": zip_info.compress_size,
            "timestamp": timestamp_from_zip_info(zip_info),
        }

    @classmethod
    def from_zip_info(cls, zip_info: ZipInfo, book_id: int) -> EpubContentsModel:
        return cls(
            book_id=book_id,
            filepath=zip_info.filename,
            filesize=zip_info.file_size,
            compressed_size=zip_info.compress_size,
            timestamp=timestamp_from_zip_info(zip_info),
        )


class EpubBookTable(SQLiteModelTable[EpubBookModel]): ...


class EpubContentsTable(SQLiteModelTable[EpubContentsModel]): ...
