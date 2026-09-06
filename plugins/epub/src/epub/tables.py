from typing import Any, TYPE_CHECKING

from sqlmodel import SQLModel, Field

from library.asserts import require
from library.epub.resources import IndexInfo
from library.database.sqlite_model_table import SQLiteModelTable
from library.image.models import ImageOptimizationResult

if TYPE_CHECKING:
    from epub.recipe_epub import EpubOptimizationResult


def _image_info_fields(info) -> dict[str, Any]:
    """The lean ImageInfo field set stored for skipped image rows."""
    return {
        "filesize": info.filesize,
        "width": info.width,
        "height": info.height,
        "format": str(info.format),
        "mode": str(info.mode),
        "bpp": info.bpp,
        "is_animated": info.is_animated,
        "n_frames": info.n_frames,
        "has_transparency_data": info.has_transparency_data,
    }


def _category_fields(info, prefix: str) -> dict[str, Any]:
    """total/images/chapters (filesize, compressed, count) for one EpubInfo,
    column names prefixed with `original_` or `new_`."""

    def triplet(index_info: IndexInfo | None) -> dict[str, int | None]:
        if index_info is None:
            return {"filesize": None, "compressed": None, "count": None}
        return {"filesize": index_info.total_size, "compressed": index_info.compress_size, "count": index_info.count}

    fields: dict[str, Any] = {}
    for category, index_info in (("total", info.total), ("images", info.images), ("chapters", info.htmls)):
        for kind, value in triplet(index_info).items():
            fields[f"{prefix}_{category}_{kind}"] = value
    return fields


class SkippedImageModel(SQLModel, table=True):
    """Skipped image optimizations of successfully processed books: skip reason
    + the untouched original info."""

    __tablename__ = "skipped_images"

    id: int | None = Field(primary_key=True)
    epub_id: int = Field(foreign_key="successful_epubs.id", index=True)
    filepath: str
    skip_reason: int
    filesize: int
    width: int
    height: int
    format: str
    mode: str
    bpp: float
    is_animated: bool
    n_frames: int
    has_transparency_data: bool | None

    @classmethod
    def from_result(cls, epub_id: int, result: ImageOptimizationResult) -> "SkippedImageModel":
        info = require(result.original_image)
        return cls(
            epub_id=epub_id,
            skip_reason=int(result.skip),
            filepath=info.path or "",
            **_image_info_fields(info),
        )


class ErrorImageModel(SQLModel, table=True):
    """Failed image optimizations: error reason + the failed placeholder info."""

    __tablename__ = "error_images"

    id: int | None = Field(primary_key=True)
    epub_id: int = Field(foreign_key="successful_epubs.id", index=True)
    error: int
    filepath: str
    filesize: int

    @classmethod
    def from_result(cls, epub_id: int, result: ImageOptimizationResult) -> "ErrorImageModel":
        info = result.original_image
        return cls(
            epub_id=epub_id,
            error=int(result.error),
            filepath=info.path or "",
            filesize=info.filesize,
        )


class SuccessfulImageModel(SQLModel, table=True):
    """Successful image optimizations: original and new info side by side."""

    __tablename__ = "successful_images"

    id: int | None = Field(primary_key=True)
    epub_id: int = Field(foreign_key="successful_epubs.id", index=True)
    original_path: str
    original_filesize: int
    original_width: int
    original_height: int
    original_format: str
    original_mode: str
    original_bpp: float
    new_path: str
    new_filesize: int
    new_width: int
    new_height: int
    new_format: str
    new_mode: str
    new_bpp: float

    @classmethod
    def from_result(cls, epub_id: int, result: ImageOptimizationResult) -> "SuccessfulImageModel":
        o = require(result.original_image)
        n = require(result.new_image)
        return cls(
            epub_id=epub_id,
            original_path=o.path or "",
            original_filesize=o.filesize,
            original_width=o.width,
            original_height=o.height,
            original_format=str(o.format),
            original_mode=str(o.mode),
            original_bpp=o.bpp,
            new_path=n.path or "",
            new_filesize=n.filesize,
            new_width=n.width,
            new_height=n.height,
            new_format=str(n.format),
            new_mode=str(n.mode),
            new_bpp=n.bpp,
        )


class SkippedEpubModel(SQLModel, table=True):
    """Skipped epub optimizations: skip reason + the untouched original info."""

    __tablename__ = "skipped_epubs"

    id: int | None = Field(primary_key=True)
    skip_reason: int
    path: str
    identifier: str | None
    author: str | None
    title: str | None
    total_filesize: int | None = None
    total_compressed: int | None = None
    total_count: int | None = None
    images_filesize: int | None = None
    images_compressed: int | None = None
    images_count: int | None = None
    chapters_filesize: int | None = None
    chapters_compressed: int | None = None
    chapters_count: int | None = None

    @classmethod
    def from_result(cls, result: "EpubOptimizationResult") -> "SkippedEpubModel":
        info = result.original_epub
        return cls(
            skip_reason=int(result.skip),
            path=str(info.path),
            identifier=info.identifier,
            author=info.author,
            title=info.title,
            **_category_fields(info, "original"),
        )


class ErrorEpubModel(SQLModel, table=True):
    """Failed epub optimizations: error reason + the failed placeholder info."""

    __tablename__ = "error_epubs"

    id: int | None = Field(primary_key=True)
    error: int
    filepath: str
    filesize: int

    @classmethod
    def from_result(cls, result: "EpubOptimizationResult") -> "ErrorEpubModel":
        info = result.original_epub
        return cls(error=int(result.error), filepath=str(info.path or ""), filesize=info.path_size)


class SuccessfulEpubModel(SQLModel, table=True):
    """Successful epub optimizations: original and new info side by side."""

    __tablename__ = "successful_epubs"

    id: int | None = Field(primary_key=True)
    path: str
    original_path: str
    identifier: str | None
    author: str | None
    title: str | None
    original_total_filesize: int
    original_total_compressed: int
    original_total_count: int
    original_images_filesize: int
    original_images_compressed: int
    original_images_count: int
    original_chapters_filesize: int
    original_chapters_compressed: int
    original_chapters_count: int
    new_total_filesize: int
    new_total_compressed: int
    new_total_count: int
    new_images_filesize: int
    new_images_compressed: int
    new_images_count: int
    new_chapters_filesize: int
    new_chapters_compressed: int
    new_chapters_count: int

    @classmethod
    def from_result(cls, result: "EpubOptimizationResult") -> "SuccessfulEpubModel":
        o = require(result.original_epub)
        n = require(result.new_epub)
        return cls(
            path=str(n.path),
            original_path=str(o.path),
            identifier=n.identifier,
            author=n.author,
            title=n.title,
            **_category_fields(o, "original"),
            **_category_fields(n, "new"),
        )


class SkippedImagesTable(SQLiteModelTable[SkippedImageModel]): ...


class ErrorImagesTable(SQLiteModelTable[ErrorImageModel]): ...


class SuccessfulImagesTable(SQLiteModelTable[SuccessfulImageModel]): ...


class SkippedEpubsTable(SQLiteModelTable[SkippedEpubModel]): ...


class ErrorEpubsTable(SQLiteModelTable[ErrorEpubModel]): ...


class SuccessfulEpubsTable(SQLiteModelTable[SuccessfulEpubModel]): ...
