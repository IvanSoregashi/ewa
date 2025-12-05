from collections.abc import Iterable
from datetime import datetime
from hashlib import md5
from typing import Any, Self, Generator
from pathlib import Path
from zipfile import ZipInfo, ZipFile
from queue import Queue

from bs4 import BeautifulSoup
from sqlmodel import SQLModel, Field, Relationship
from epub.utils import ts_to_dt, bt_to_mb, timestamp_from_zip_info, string_to_int_hash
from ewa.ui import print_error


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

    def update_from_opf_file(self, opf_bytes: bytes) -> None:
        self.opf_hash = md5(opf_bytes).hexdigest()
        soup = BeautifulSoup(opf_bytes, "xml")
        metadata = soup.find("metadata")
        print(metadata)
        if metadata:
            language = metadata.find("dc:language")
            identifier = metadata.find("dc:identifier")
            self.identifier = None
            if identifier is not None:
                id_id = identifier.get("id", "")
                id_schema = identifier.get("opf:schema", "")
                id_text = identifier.text or ""
                self.identifier = f"{id_id}:{id_schema}:{id_text}"
            title = metadata.find("dc:title")
            self.title = title and title.text

            creator = metadata.find("dc:creator")
            self.creator = None
            if creator is not None:
                creator_as = creator and creator.get("opf:file-as", "")
                creator_text = creator.text
                self.creator = f"{creator_as}:{creator_text}"

            date = metadata.find("dc:date")
            meta = metadata.find_all("opf:meta")
            self.datetime = (date and date.text) or (meta and meta.get("content"))
        print(self)



class EpubContents(SQLModel, table=True):
    book_id: int = Field(foreign_key="epubbook.id", primary_key=True)
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
            "timestamp": timestamp_from_zip_info(zip_info)
        }

    @classmethod
    def from_zip_info(cls, book_id: int, zip_info: ZipInfo) -> EpubContents:
        return cls(
            book_id=book_id,
            filepath=zip_info.filename,
            filesize=zip_info.file_size,
            compressed_size=zip_info.compress_size,
            timestamp=timestamp_from_zip_info(zip_info)
        )


def scan_file(path: Path, q: Queue) -> EpubBook:
    book_id = string_to_int_hash(str(path))
    stat = path.stat()
    book = EpubBook(
        id=book_id,
        filepath=str(path.absolute()),
        filesize=stat.st_size,
        mtime=int(stat.st_mtime),
        ctime=int(stat.st_ctime),
    )
    with ZipFile(path) as zip_file:
        for info in zip_file.infolist():
            q.put(EpubContents.dict_from_zip_info(book_id, info))
            if not info.filename.endswith(".opf"):
                continue
            with zip_file.open(info.filename) as file:
                opf_bytes = file.read()
                book.update_from_opf_file(opf_bytes)

    return book

