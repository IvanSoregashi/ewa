from typing import Any
from pathlib import Path
from zipfile import ZipInfo

from sqlmodel import SQLModel, Field, Relationship
from epub.utils import timestamp_from_zip_info, string_to_int_hash
from ewa.sqlite_model_table import SQLiteModelTable


class EpubFileModel(SQLModel, table=True):
    __tablename__ = "epub_files"

    id: int | None = Field(primary_key=True)
    filepath: str = Field(index=True)
    filesize: int
    mtime: int
    ctime: int

    mimetype: bool = False
    container: bool = False
    content: bool = False
    opf: str | None = None
    toc: bool = False
    ncx: str | None = None
    serene_panda: bool = False
    serene_panda_ttf: str | None = None

    contents: list[EpubContentsModel] = Relationship(back_populates="book")

    @classmethod
    def from_path(cls, path: Path) -> EpubFileModel:
        stat = path.stat()
        return cls(
            id=string_to_int_hash(str(path)),
            filepath=str(path.absolute()),
            filesize=stat.st_size,
            mtime=int(stat.st_mtime),
            ctime=int(stat.st_ctime),
        )

    def process_filenames(self, filenames: list[str]) -> None:
        self.mimetype = "mimetype" in filenames
        self.container = "META-INF/container.xml" in filenames
        self.content = "content.opf" in filenames
        if not self.content:
            self.opf = "".join(fn for fn in filenames if fn.endswith(".opf"))
        self.toc = "toc.ncx" in filenames
        if not self.toc:
            self.ncx = "".join(fn for fn in filenames if fn.endswith(".ncx"))
        serene_panda = [fn for fn in filenames if fn.lower().endswith("serenepanda.ttf")]
        self.serene_panda = bool(serene_panda)
        if serene_panda:
            self.serene_panda_ttf = serene_panda[0]

    def to_epub(self):
        from epub.epub_classes import EPUB

        return EPUB.from_epub_model(self)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()  # TODO: proper formatting

    def as_list(self) -> list:
        return list(map(str, self.as_dict().values()))  # TODO: proper formatting


class EpubContentsModel(SQLModel, table=True):
    __tablename__ = "files_in_epub"

    book_id: int = Field(primary_key=True, foreign_key="epub_files.id")
    filepath: str = Field(primary_key=True)
    filesize: int
    compressed_size: int
    timestamp: int

    book: EpubFileModel = Relationship(back_populates="contents")

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


class EpubTableOfContentsModel(SQLModel, table=True):
    __tablename__ = "table_of_contents"

    book_id: int = Field(primary_key=True, foreign_key="epub_files.id")
    filesize: int


class EpubBookTable(SQLiteModelTable[EpubFileModel]): ...


class EpubContentsTable(SQLiteModelTable[EpubContentsModel]): ...
