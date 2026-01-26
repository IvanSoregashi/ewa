from __future__ import annotations

import shutil
import tempfile
import logging

from queue import Queue
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
from collections.abc import Iterable, Generator
from concurrent.futures.thread import ThreadPoolExecutor

from library.database.sqlite_model_table import TERMINATOR
from ewa.ui import print_error
from epub.epub_state import EpubIllustrations
from epub.tables import EpubFileModel, EpubContentsModel, EpubBookTable
from epub.utils import string_to_int_hash
from epub.file_parsing import parse_epub_xml
from epub.constants import quarantine_dir

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
    def __init__(self, path: Path, book_id: int | None = None, book_model: EpubFileModel | None = None) -> None:
        self.path = path
        self.book_id = book_id or string_to_int_hash(str(path))
        self.book_model = book_model
        self.book_contents_models: list[EpubContentsModel] | None = None

    @classmethod
    def from_epub_model(cls, model: EpubFileModel):
        return cls(
            path=Path(model.filepath),
            book_id=model.id,
            book_model=model,
        )

    def extract(self) -> UnpackedEPUB:
        unpacked_directory = Path(tempfile.mkdtemp())
        unpacked_directory.mkdir(parents=True, exist_ok=True)
        with ZipFile(self.path) as zip_file:
            zip_file.extractall(unpacked_directory)
        return UnpackedEPUB(unpacked_directory, self.path.name)

    def extract_file(self, destination_dir: str, filepath: str):
        with ZipFile(self.path) as zip_file:
            font_bytes = zip_file.read(filepath)
            hash_num = string_to_int_hash(font_bytes)
            new_filename = f"{hash_num}_{Path(filepath).name}"
            new_filepath = Path(destination_dir) / new_filename
            if not new_filepath.exists():
                new_filepath.write_bytes(font_bytes)

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
            self.book_model = EpubFileModel.from_path(self.path)

    def full_scan(self, overwrite: bool = True):
        self.path_scan()
        if overwrite or self.book_contents_models is None:
            self.book_contents_models = []
        with ZipFile(self.path) as zip_file:
            for info in zip_file.infolist():
                self.book_contents_models.append(EpubContentsModel.from_zip_info(info, self.book_id))
                if not info.filename.endswith(".opf"):
                    continue
                with zip_file.open(info.filename) as file:
                    opf_bytes = file.read()
                    self.book_model.update_from_opf_file(opf_bytes)

    def read_from_database(self, table: EpubBookTable):
        self.book_model = table.get_one(id=self.book_id)
        self.book_contents_models = self.book_model.contents


class ScanEpubsInDirectory:
    def __init__(
        self,
        directory: Path,
        mask: str = "*.epub",
        queue: Queue[dict] = Queue(),
        workers: int = 0,
    ) -> None:
        self.directory = directory
        self.mask = mask
        self.paths: Iterable[Path] = (path for path in directory.rglob(mask) if not quarantine_dir in path.parents)
        self.workers = workers
        self.queue = queue

    def process_epub(self, path: Path) -> EpubFileModel | None:
        try:
            book = EpubFileModel.from_path(path)
            book_id = book.id
        except Exception as e:
            logger.error(f"process_epub({path}): failed to load book: {e}")
            return None
        try:
            filenames = []
            with ZipFile(path) as zip_file:
                parsed_data = parse_epub_xml(zipfile=zip_file)
                book.read_metadata(parsed_data)
                data = parsed_data.get("data", {})

                for info in zip_file.infolist():
                    fdata = data.get(info.filename, {})
                    self.queue.put(EpubContentsModel.dict_from_zip_info(info, book_id, fdata))
                    filenames.append(info.filename)

            book.process_filenames(filenames)
        except Exception as e:
            logger.error(f"process_epub({path}): failed to process zipfile, quarantining: {e}")
            path.rename(quarantine_dir / path.name)
        return book

    def _process_paths(self) -> Generator[EpubFileModel, None, None]:
        if self.workers:
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                yield from filter(None, executor.map(self.process_epub, self.paths))
        else:
            yield from filter(None, map(self.process_epub, self.paths))
        self.queue.put(TERMINATOR)

    def do_scan(self):
        return list(self._process_paths())

    def do_scan_with_progress(self):
        books = []
        self.paths = list(self.paths)
        total = len(self.paths)
        current = 0
        print("[green]Scanning...", current, total)
        for book in self._process_paths():
            books.append(book)
            current += 1
            if current % 25 == 0:
                print("[green]Scanning...", current, total)
        print("[green]Scanning...", current, total)
        return books
