from __future__ import annotations

import shutil
import tempfile
import logging
import time
import os

from typing import Iterator, Generator
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

# import pandas as pd

from library.image.image_processor import ImageProcessingResult, ImageProcessor
from library.image.image_optimization_settings import ImageSettings
from library.markup.chapter_processor import EpubChapters

logger = logging.getLogger(__name__)


@dataclass
class ZipMixin:
    ziplike_path: Path
    unpacked_directory: Path | None = None

    def _extract(self, directory: Path | None = None) -> None:
        if self.ziplike_path is None:
            raise ValueError("ziplike_path is not set")
        if directory is not None:
            self.unpacked_directory = directory
        if self.unpacked_directory is None:
            self.unpacked_directory = Path(tempfile.mkdtemp())
        else:
            self.unpacked_directory.mkdir(parents=True, exist_ok=True)
        with ZipFile(self.ziplike_path) as zip_file:
            zip_file.extractall(self.unpacked_directory)

    def _teardown(self) -> None:
        if self.unpacked_directory and self.unpacked_directory.exists():
            shutil.rmtree(self.unpacked_directory)
            self.unpacked_directory = None

    def iterate(self) -> Iterator[ZipInfo]:
        with ZipFile(self.ziplike_path) as zip_file:
            for info in zip_file.infolist():
                yield info


@dataclass
class UnpackedEpub(ZipMixin):
    # Paths
    output_path: Path | None = None
    # user_directory: EpubUserDirectory = field(default_factory=EpubUserDirectory)

    chapters: EpubChapters | None = None
    illustrations: EpubIllustrations | None = None

    def _compact_epub(self, directory: Path) -> Path:
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"UnpackedEpub._compact: directory {directory} does not exist")
        if not self.unpacked_directory.exists() or not self.unpacked_directory.is_dir():
            raise FileNotFoundError(
                f"temporary_directory: temporary_directory {self.unpacked_directory} does not exist"
            )
        path = directory / self.ziplike_path.name
        while path.exists():
            path = path.with_stem(path.stem + "+")
        try:
            with ZipFile(path, "w") as zipf:
                mimetype_file = self.unpacked_directory / "mimetype"
                if mimetype_file.exists():
                    zipf.write(mimetype_file, arcname="mimetype", compress_type=ZIP_STORED)
                else:
                    raise FileNotFoundError("Missing required 'mimetype' file for EPUB.")

                for file in self.unpacked_directory.rglob("*"):
                    if file.is_file() and file.name != "mimetype":
                        arcname = file.relative_to(self.unpacked_directory)
                        zipf.write(file, arcname=arcname, compress_type=ZIP_DEFLATED)
            return path
        except Exception as e:
            logger.error(f"temporary_directory: failed to compress directory into EPUB: {e}")
            raise e
        finally:
            self._teardown()

    def optimize(self, image_settings: ImageSettings) -> OptimizeResult:
        start_time = time.time()
        result = OptimizeResult()
        result.original_epub_path = self.ziplike_path
        result.original_epub_size = self.ziplike_path.stat().st_size
        try:
            self._extract()
            self.chapters = EpubChapters(self.unpacked_directory)
            self.illustrations = EpubIllustrations(self.unpacked_directory, image_settings)
            result.optimization_results = self.illustrations.optimize_images_in_sync()
            result.optimization_time = self.illustrations.optimization_time
            result.optimization_success = all(op_result.success for op_result in result.optimization_results)
            assert result.optimization_success, "Some images failed to resize"
            result.chapter_success = self.chapters.update_image_references(result.image_rename_dict())
            result.chapter_time = self.chapters.update_time
            result.chapter_report = self.chapters.detailed_report()
            assert result.chapter_report, "Failed to update image references"
            result.resized_epub_path = self._compact_epub(self.user_directory.resized_dir)
            result.resized_epub_size = result.resized_epub_path.stat().st_size
            result.success = True
        except Exception as e:
            result.error = str(e)
            result.success = False
            self._teardown()
        result.total_time = time.time() - start_time
        return result

    def measure_optimized_size(self, image_settings: ImageSettings) -> OptimizeResult:
        start_time = time.time()
        result = OptimizeResult()
        result.original_epub_path = self.ziplike_path
        result.original_epub_size = self.ziplike_path.stat().st_size
        try:
            self._extract()
            self.illustrations = EpubIllustrations(self.unpacked_directory, image_settings)
            result.optimization_results = self.illustrations.optimize_images_in_sync()
            result.optimization_time = self.illustrations.optimization_time
            result.optimization_success = all(op_result.success for op_result in result.optimization_results)
            result.success = True
        except Exception as e:
            result.error = str(e)
            result.success = False
        self._teardown()
        result.total_time = time.time() - start_time
        return result


@dataclass
class OptimizeResult:
    # Resize results
    optimization_results: list[ImageProcessingResult] = field(default_factory=list)
    optimization_time: float = 0
    optimization_success: bool = False

    # Validation results
    validation_report: list[dict] = field(default_factory=list)
    validation_time: float = 0
    validation_success: bool = True

    # Chapter results
    chapter_report: list[dict] = field(default_factory=list)
    chapter_time: float = 0
    chapter_success: bool = False

    # Total results
    success: bool = False
    total_time: float = 0
    error: str = ""

    original_epub_path: Path | None = None
    original_epub_size: float = 0
    resized_epub_path: Path | None = None
    resized_epub_size: float = 0

    def image_rename_dict(self) -> dict[str, str]:
        return {img.name: img.new_image.path.name for img in self.optimization_results if img.renamed}

    def report_line_success(self) -> dict:
        return {
            "name": self.original_epub_path.name,
            "time": f"{self.total_time:.2f} s",
            "original_size": f"{self.original_epub_size / 1024 / 1024:.2f} mb",
            "compressed_to": f"{self.resized_epub_size / self.original_epub_size * 100:.2f}%",
        }

    def report_line_failure(self) -> dict:
        return {
            "name": self.original_epub_path.name,
            "time": f"{self.total_time:.2f} s",
            "original_size": f"{self.original_epub_size / 1024 / 1024:.2f} mb",
            "error": self.error[:50],
        }

    def report_line_resize(self) -> dict:
        old_image_size = sum(rr["old_size"] for rr in self.optimization_results)
        new_image_size = sum(rr["new_size"] for rr in self.optimization_results)
        compression = round(new_image_size / old_image_size * 100, 2)
        images = len(self.optimization_results)
        # errors = len([rr for rr in self.resize_report if rr["error"]])
        return {
            "name": self.original_epub_path.name,
            "time": f"{self.total_time:.2f} s",
            "images": images,
            "old_size": f"{old_image_size / 1024 / 1024:.2f} mb",
            "compressed_to": f"{compression:.2f}%",
            "success": self.optimization_success,
        }


@dataclass
class EpubIllustrations:
    epub_temp_dir: Path

    image_settings: "ImageSettings"

    optimization_time: float = 0

    @property
    def actual_size(self) -> int:
        return sum(p.stat().st_size for p in self.iter_image_paths())

    def iter_image_paths(self) -> Generator[Path, None, None]:
        for path in self.epub_temp_dir.glob("EPUB/images/*.*"):
            yield path

    def optimize_images_in_threads(self) -> list[ImageProcessingResult]:
        start_time = time.time()
        processor = ImageProcessor(self.image_settings)
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            results = list(executor.map(processor.optimize_image, self.iter_image_paths()))
        self.optimization_time = time.time() - start_time
        return results

    def optimize_images_in_sync(self) -> list[ImageProcessingResult]:
        start_time = time.time()
        processor = ImageProcessor(self.image_settings)
        results = list(map(processor.optimize_image, self.iter_image_paths()))
        self.optimization_time = time.time() - start_time
        return results
