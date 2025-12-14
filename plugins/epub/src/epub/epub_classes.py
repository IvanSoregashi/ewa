from __future__ import annotations

import os
import shutil
import tempfile
import logging

from queue import Queue
from typing import Any, overload
from pathlib import Path
from hashlib import md5
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
from functools import partial
from collections.abc import Iterable, Generator
from concurrent.futures.thread import ThreadPoolExecutor

from bs4 import BeautifulSoup

from ewa.main import settings
from ewa.ui import print_error
from epub.epub_state import EpubIllustrations
from epub.tables import EpubBookModel, EpubContentsModel
from epub.utils import string_to_int_hash

from library.image.image_optimization_settings import ImageSettings
from library.markup.chapter_processor import EpubChapters

logger = logging.getLogger(__name__)


class UnpackedEPUB:
    def __init__(self, path: Path, name: str) -> None:
        self.path = path
        self.name = name

    @property
    def chapters(self) -> EpubChapters:
        return EpubChapters(self.path / "EPUB" / "chapters")

    @property
    def images(self) -> EpubIllustrations:
        return EpubIllustrations(self.path / "EPUB" / "images", ImageSettings())

    def compress(self, destination_folder: Path) -> EPUB:
        if not destination_folder.exists() or not destination_folder.is_dir():
            raise FileNotFoundError(f"UnpackedEPUB.compress: directory {destination_folder} does not exist")
        if not self.path.exists() or not self.path.is_dir():
            raise FileNotFoundError(f"temporary_directory: temporary_directory {self.path} does not exist")

        path = destination_folder / self.name
        while path.exists():
            path = path.with_stem(path.stem + "+")

        try:
            with ZipFile(path, "w") as zipf:
                mimetype_file = self.path / "mimetype"
                if mimetype_file.exists():
                    zipf.write(mimetype_file, arcname="mimetype", compress_type=ZIP_STORED)
                else:
                    raise FileNotFoundError("Missing required 'mimetype' file for EPUB.")

                for file in self.path.rglob("*"):
                    if file.is_file() and file.name != "mimetype":
                        arcname = file.relative_to(self.path)
                        zipf.write(file, arcname=arcname, compress_type=ZIP_DEFLATED)
            return EPUB(path)
        except Exception as e:
            logger.error(f"temporary_directory: failed to compress directory into EPUB: {e}")
            raise e
        finally:
            self.delete()

    def delete(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
            self.path = None


class EPUB:
    def __init__(self, path: Path, book_id: int | None = None) -> None:
        self.path = path
        self.book_id = book_id or string_to_int_hash(str(path))
        self.book_model: EpubBookModel | None = None
        self.book_contents_models: list[EpubContentsModel] | None = None

    def extract(self) -> UnpackedEPUB:
        unpacked_directory = Path(tempfile.mkdtemp())
        unpacked_directory.mkdir(parents=True, exist_ok=True)
        with ZipFile(self.path) as zip_file:
            zip_file.extractall(unpacked_directory)
        return UnpackedEPUB(unpacked_directory, self.path.name)

    def delete_file(self):
        self.path.unlink(missing_ok=True)

    def move_original_to(self, directory: Path, overwrite: bool = True, try_rename: bool = True) -> bool:
        path = directory / self.path.name
        while (not overwrite) and path.exists():
            path = path.with_stem(path.stem + "+")

        if try_rename:
            try:
                self.path.rename(path)
                self.path = path
                return True
            except OSError as e:
                print_error(f"move_original os: failed to move file: {e}")
            except Exception as e:
                print_error(f"move_original: failed to move file: {e}")

        try:
            shutil.copy2(self.path, path)
            self.path.unlink(missing_ok=True)
            self.path = path
            return True
        except Exception as e:
            print_error(f"move_original: failed to copy file: {e}")
        return False

    def path_scan(self, overwrite: bool = True):
        if overwrite or self.book_model is None:
            self.book_model = EpubBookModel.from_path(self.path)

    def full_scan(self, overwrite: bool = True):
        self.path_scan()
        if overwrite or self.book_contents_models is None:
            self.book_contents_models = []
        with ZipFile(self.path) as zip_file:
            for info in zip_file.infolist():
                self.book_contents_models.append(EpubContentsModel.from_zip_info(self.book_id, info))
                if not info.filename.endswith(".opf"):
                    continue
                with zip_file.open(info.filename) as file:
                    opf_bytes = file.read()
                    self.book_model.update_from_opf_file(opf_bytes)


class ScanDirectoryEPUB:
    def __init__(
        self,
        directory: Path,
        mask: str = "*.epub",
        queue: Queue[dict] = Queue(),
        workers: int = 0,
    ) -> None:
        self.directory = directory
        self.mask = mask
        self.workers = workers
        self.queue = queue

    def process_epub(self, path: Path) -> EpubBookModel | None:
        try:
            book = EpubBookModel.from_path(path)
            book_id = book.id
        except Exception as e:
            logger.error(f"process_epub({path}): failed to load book: {e}")
            return None
        try:
            with ZipFile(path) as zip_file:
                for info in zip_file.infolist():
                    self.queue.put(EpubContentsModel.dict_from_zip_info(info, book_id))
                    if info.filename.endswith(".opf"):
                        book.update_from_opf_file(zip_file.read(info.filename))
        except Exception as e:
            logger.error(f"process_epub({path}): failed to process zipfile: {e}")
        return book

    def _process_paths(self) -> Generator[EpubBookModel, None, None]:
        iter_paths = self.directory.rglob(self.mask)
        if self.workers:
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                yield from filter(None, executor.map(self.process_epub, iter_paths))
        else:
            yield from filter(None, map(self.process_epub, iter_paths))

    def do_scan(self):
        yield from self._process_paths()


def content_dicts_from_path(
    path: Path, book_id: int | None = None, q: Queue[dict] | None = None
) -> tuple[bytes, list[dict]] | bytes:
    if book_id is None:
        book_id = string_to_int_hash(str(path))
    contents = []
    opf_bytes: bytes
    with ZipFile(path) as zip_file:
        for info in zip_file.infolist():
            finfo = EpubContentsModel.dict_from_zip_info(info, book_id)
            contents.append(finfo)
            if info.filename.endswith(".opf"):
                opf_bytes = zip_file.read(info.filename)
    if q is not None:
        for d in contents:
            q.put(d)
        return opf_bytes
    return opf_bytes, contents


def content_models_from_path(path: Path, book_id: int | None = None) -> tuple[bytes, list[EpubContentsModel]]:
    if book_id is None:
        book_id = string_to_int_hash(str(path))
    contents = []
    opf_bytes: bytes
    with ZipFile(path) as zip_file:
        for info in zip_file.infolist():
            finfo = EpubContentsModel.from_zip_info(info, book_id)
            contents.append(finfo)
            if info.filename.endswith(".opf"):
                opf_bytes = zip_file.read(info.filename)
    return opf_bytes, contents


def read_book_contents(book: EpubBookModel, q: Queue[dict] | None = None) -> EpubBookModel:
    opf_bytes, contents = content_dicts_from_path(Path(book.filepath), book.id)
    book.update_from_opf_file(opf_bytes)

    return book


def content_from_books_q(
    books: Iterable[EpubBookModel], q: Queue[dict[str, str]]
) -> Generator[EpubBookModel, None, None]:
    for book in books:
        with ZipFile(book.filepath) as zip_file:
            for info in zip_file.infolist():
                q.put(EpubContentsModel.dict_from_zip_info(book.book_id, info))
                if info.filename.endswith(".opf"):
                    book.update_from_opf_file(zip_file.read(info.filename))
        yield book


def book_content_in_thread(book: EpubBookModel) -> tuple[EpubBookModel, list[dict]]:
    contents = []
    with ZipFile(book.filepath) as zip_file:
        for info in zip_file.infolist():
            finfo = EpubContentsModel.dict_from_zip_info(book.book_id, info)
            contents.append(finfo)
            if info.filename.endswith(".opf"):
                book.update_from_opf_file(zip_file.read(info.filename))
    return book, contents


def gen_content_from_book(book: EpubBookModel) -> Generator[dict, None, None]:
    with ZipFile(book.filepath) as zip_file:
        for info in zip_file.infolist():
            yield EpubContentsModel.dict_from_zip_info(info, book.book_id)


def gen_content_from_books(books: Iterable[EpubBookModel]) -> Generator[dict, None, None]:
    for book in books:
        yield from gen_content_from_book(book)


def scan_directory(directory: Path, mask: str = "*.epub"):
    iter_paths = directory.rglob(mask)
    iter_models = map(EpubBookModel.from_path, iter_paths)
    iter_content = gen_content_from_books(iter_models)
