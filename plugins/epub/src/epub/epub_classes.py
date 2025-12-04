from __future__ import annotations

import shutil
import tempfile
import logging

from typing import Any
from pathlib import Path
from hashlib import md5
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from bs4 import BeautifulSoup

from epub.epub_state import EpubIllustrations
from epub.tables import EpubContentData
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
            raise FileNotFoundError(
                f"UnpackedEPUB.compress: directory {destination_folder} does not exist"
            )
        if not self.path.exists() or not self.path.is_dir():
            raise FileNotFoundError(
                f"temporary_directory: temporary_directory {self.path} does not exist"
            )

        path = destination_folder / self.name
        while path.exists():
            path = path.with_stem(path.stem + "+")

        try:
            with ZipFile(path, "w") as zipf:
                mimetype_file = self.path / "mimetype"
                if mimetype_file.exists():
                    zipf.write(
                        mimetype_file, arcname="mimetype", compress_type=ZIP_STORED
                    )
                else:
                    raise FileNotFoundError(
                        "Missing required 'mimetype' file for EPUB."
                    )

                for file in self.path.rglob("*"):
                    if file.is_file() and file.name != "mimetype":
                        arcname = file.relative_to(self.path)
                        zipf.write(file, arcname=arcname, compress_type=ZIP_DEFLATED)
            return EPUB(path)
        except Exception as e:
            logger.error(
                f"temporary_directory: failed to compress directory into EPUB: {e}"
            )
            raise e
        finally:
            self.delete()

    def delete(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
            self.path = None


class EPUB:
    def __init__(self, path: Path) -> None:
        self.path = path

    def extract(self) -> UnpackedEPUB:
        unpacked_directory = Path(tempfile.mkdtemp())
        unpacked_directory.mkdir(parents=True, exist_ok=True)
        with ZipFile(self.path) as zip_file:
            zip_file.extractall(unpacked_directory)
        return UnpackedEPUB(unpacked_directory, self.path.name)

    def delete(self):
        self.path.unlink(missing_ok=True)

    def move_original(self, directory: Path) -> Path:
        if not self.path.exists() or not directory.exists():
            raise FileNotFoundError(
                f"EPUBState.move_original: EPUB file {self.path} does not exist"
            )
        path = directory / self.path.name

        while path.exists():
            path = path.with_stem(path.stem + "+")

        try:
            shutil.copy2(self.path, path)
            self.path.unlink(missing_ok=True)
            self.path = path
            return self.path
        except Exception as e:
            print(f"move_original: failed to copy file: {e}")

    def hash(self, opf_file: str | None = None) -> str:
        with ZipFile(self.path) as zip_file:
            if opf_file is None:
                for info in zip_file.infolist():
                    if info.filename.lower().endswith(".opf"):
                        opf_file = info.filename
                        break
            with zip_file.open(opf_file) as file:
                return md5(file.read()).hexdigest()

    def collect_file_info(self) -> list[EpubContentData]:
        with ZipFile(self.path) as zip_file:
            all_files: list[EpubContentData] = []
            opf_hash = None
            for info in zip_file.infolist():
                result = EpubContentData.from_zip_info(self.path, info)
                all_files.append(result)
                if result.suffix != ".opf":
                    continue
                with zip_file.open(info.filename) as file:
                    opf_hash = md5(file.read()).hexdigest()
            for d in all_files:
                d.opf_hash = opf_hash
            return all_files

    def file_info(self, opf_file: str | None = None) -> dict:
        with ZipFile(self.path) as zip_file:
            result: dict[str, Any] = {
                "path": self.path,
                "size": self.path.stat().st_size,
                "hash": self.hash(),
            }
            if opf_file is None:
                for info in zip_file.infolist():
                    if info.filename.lower().endswith(".opf"):
                        opf_file = info.filename
                        break
            with zip_file.open(opf_file) as file:
                soup = BeautifulSoup(file, "xml")
                metadata = soup.find("metadata")
                if metadata:
                    identifier = metadata.find("dc:identifier")
                    title = metadata.find("dc:title")
                    creator = metadata.find("dc:creator")
                    result["id"] = identifier and identifier.text
                    result["title"] = title and title.text
                    result["creator"] = creator and creator.text
                    result["creator_as"] = creator and creator.get("opf:file-as", "")
                    date = metadata.find("dc:date")
                    meta = metadata.find("opf:meta")
                    timestamp = (date and date.text) or (
                        meta and meta.get("content", "")
                    )
                    result["timestamp"] = timestamp
            return result
