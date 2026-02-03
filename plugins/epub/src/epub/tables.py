import re
from typing import Any
from pathlib import Path
from zipfile import ZipInfo
from sqlmodel import SQLModel, Field, Relationship

from epub.utils import timestamp_from_zip_info, string_to_int_hash, bt_to_mb
from library.database.sqlite_model_table import SQLiteModelTable


class EpubFileModel(SQLModel, table=True):
    __tablename__ = "epub_files"

    id: int | None = Field(primary_key=True)
    filepath: str = Field(index=True)
    filesize: int
    mtime: int
    ctime: int

    language: str | None = None
    title: str | None = None
    creator: str | None = None
    identifier: str | None = None

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

    def read_metadata(self, data: dict) -> None:
        metadata = data.get("metadata", {})
        self.language = str(metadata.get("language", "")) or None
        self.title = str(metadata.get("title", "")) or None
        self.creator = str(metadata.get("creator", "")) or None
        self.identifier = str(metadata.get("identifier", "")) or None

    def get_contents_tuples(self, fields: list[str]):
        result = []
        for item in self.contents:
            dct = item.model_dump()
            result.append(tuple(dct.get(field) for field in fields))
        return result

    def get_contents(self):
        tuples = self.get_contents_tuples(["filepath", "filesize"])
        return tuples

    def to_epub(self):
        from epub.epub_classes import EPUB

        return EPUB.from_epub_model(self)

    def as_dict(self) -> dict[str, Any]:
        return {"filepath": self.filepath, "filesize": bt_to_mb(self.filesize), "creator": self.creator}

    def as_list(self) -> list:
        return list(map(str, self.as_dict().values()))  # TODO: proper formatting

    def comparable_string(self) -> str:
        string = Path(self.filepath).stem + " " + self.title
        string = string.replace("_", " ").replace("+", " ").replace("  ", " ").strip()
        string = re.sub(r"\[.*?\]|\(.*?\)", "", string)
        string = re.sub(r"\d+-\d+", "", string)
        string = "".join(map(lambda x: x if x.isalnum() else " ", string)).replace("  ", " ")
        return string.strip().lower()


class EpubContentsModel(SQLModel, table=True):
    __tablename__ = "files_in_epub"

    book_id: int = Field(primary_key=True, foreign_key="epub_files.id")
    filepath: str = Field(primary_key=True)
    filesize: int
    compressed_size: int
    timestamp: int

    item_id: str | None = None
    media_type: str | None = None
    chapter: str | None = None

    orphan: bool = False

    book: EpubFileModel = Relationship(back_populates="contents")

    @staticmethod
    def dict_from_zip_info(zip_info: ZipInfo, book_id: int, data: dict) -> dict[str, Any]:
        return {
            "book_id": book_id,
            "filepath": zip_info.filename,
            "filesize": zip_info.file_size,
            "compressed_size": zip_info.compress_size,
            "timestamp": timestamp_from_zip_info(zip_info),
            "item_id": data.get("item_id"),
            "media_type": data.get("media_type"),
            "chapter": data.get("chapter"),
            "orphan": False,
        }

    @staticmethod
    def from_orphaned_dict(filename: str, book_id: int, data: dict) -> dict[str, Any]:
        return {
            "book_id": book_id,
            "filepath": filename,
            "filesize": 0,
            "compressed_size": 0,
            "timestamp": 0,
            "item_id": data.get("item_id"),
            "media_type": data.get("media_type"),
            "chapter": data.get("chapter"),
            "orphan": True,
        }

    @classmethod
    def from_zip_info(cls, zip_info: ZipInfo, book_id: int, data: dict) -> EpubContentsModel:
        return cls(
            book_id=book_id,
            filepath=zip_info.filename,
            filesize=zip_info.file_size,
            compressed_size=zip_info.compress_size,
            timestamp=timestamp_from_zip_info(zip_info),
            item_id=data.get("item_id"),
            media_type=data.get("media_type"),
            chapter=data.get("chapter"),
        )

    @classmethod
    def from_orphan(cls, filename: str, book_id: int, data: dict) -> EpubContentsModel:
        return cls(
            book_id=book_id,
            filepath=filename,
            filesize=0,
            compressed_size=0,
            timestamp=0,
            item_id=data.get("item_id"),
            media_type=data.get("media_type"),
            chapter=data.get("chapter"),
            orphan=True,
        )

class EpubBookTable(SQLiteModelTable[EpubFileModel]):
    def get_encrypted_epubs(self):
        return self.get_many(self.model.serene_panda == True, limit=10000)


class EpubContentsTable(SQLiteModelTable[EpubContentsModel]): ...
