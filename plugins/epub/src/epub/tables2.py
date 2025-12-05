from hashlib import md5
from typing import Any
from pathlib import Path
from zipfile import ZipInfo, ZipFile
from queue import Queue

from bs4 import BeautifulSoup
from sqlmodel import SQLModel, Field, Relationship
from epub.utils import timestamp_from_zip_info, string_to_int_hash


class EpubBook(SQLModel, table=True):
    id: int | None = Field(primary_key=True)
    filepath: str = Field(index=True)
    filesize: int
    mtime: int
    ctime: int

    opf_hash: str | None = None
    title: str | None = None
    creator: str | None = None

    contents: list[EpubContents] = Relationship(back_populates="book")

    @classmethod
    def from_path(cls, path: Path) -> EpubBook:
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


class EpubContents(SQLModel, table=True):
    book_id: int = Field(primary_key=True, foreign_key="epubbook.id")
    filepath: str = Field(primary_key=True)
    filesize: int
    compressed_size: int
    timestamp: int

    book: EpubBook = Relationship(back_populates="contents")

    @staticmethod
    def dict_from_zip_info(book_id: int, zip_info: ZipInfo) -> dict[str, Any]:
        return {
            "book_id": book_id,
            "filepath": zip_info.filename,
            "filesize": zip_info.file_size,
            "compressed_size": zip_info.compress_size,
            "timestamp": timestamp_from_zip_info(zip_info),
        }

    @classmethod
    def from_zip_info(cls, book_id: int, zip_info: ZipInfo) -> EpubContents:
        return cls(
            book_id=book_id,
            filepath=zip_info.filename,
            filesize=zip_info.file_size,
            compressed_size=zip_info.compress_size,
            timestamp=timestamp_from_zip_info(zip_info),
        )


def scan_file(path: Path, q: Queue) -> EpubBook:
    book = EpubBook.from_path(path)
    with ZipFile(path) as zip_file:
        for info in zip_file.infolist():
            q.put(EpubContents.dict_from_zip_info(book.book_id, info))
            if not info.filename.endswith(".opf"):
                continue
            with zip_file.open(info.filename) as file:
                opf_bytes = file.read()
                book.update_from_opf_file(opf_bytes)
    return book
