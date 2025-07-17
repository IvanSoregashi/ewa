from __future__ import annotations

import shutil
import tempfile
import logging
import time

from typing import Any
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


import pandas as pd

from ewa.utils.epub.image_processor import EpubIllustrations, ImageOptimizationSettings
from ewa.utils.epub.chapter_processor import EpubChapters

logger = logging.getLogger(__name__)


@dataclass
class EpubUserDirectory:
    directory: Path = Path("~/Downloads/EPUB").expanduser().absolute()
    quarantine_dir: Path = directory / "Quarantine"
    resized_dir: Path = directory / "Resized"
    unchanged_dir: Path = directory / "Unchanged"
    processed_dir: Path = directory / "Processed"

    def __post_init__(self) -> None:
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.resized_dir.mkdir(parents=True, exist_ok=True)
        self.unchanged_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class FileStat:
    path: Path
    size: int
    suffix: str
    name: str
    directory: Path

    @classmethod
    def from_zip_info(cls, info: ZipInfo) -> FileStat:
        return cls(
            path=info.filename,
            size=info.file_size,
            suffix=info.filename.split(".")[-1],
            name=Path(info.filename).name,
            directory=Path(info.filename).parent
        )

    @classmethod
    def from_path(cls, path: Path, relative_directory: Path) -> FileStat:
        return cls(
            path=path,
            size=path.stat().st_size,
            suffix=path.suffix.lower(),
            name=path.stem,
            directory=path.parent.relative_to(relative_directory)
        )

@dataclass
class StatReport:
    name: str
    files: int
    size: float
    percentage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": str(self.name),
            "files": int(self.files),
            "size": f"{float(self.size)} mb",
            "percentage": f"{float(self.percentage)}%"
        }


@dataclass
class OptimizeResult:
    # Resize results
    resize_success: bool = False
    resize_time: float = 0
    resize_report: list[dict] = field(default_factory=list)

    # Validation results
    validation_success: bool = True
    validation_time: float = 0
    validation_report: list[dict] = field(default_factory=list)

    # Chapter results
    chapter_success: bool = False
    chapter_time: float = 0
    chapter_report: list[dict] = field(default_factory=list)

    # Total results
    success: bool = False
    total_time: float = 0
    error: str = ""

    original_epub_path: Path | None = None
    original_epub_size: float = 0
    resized_epub_path: Path | None = None
    resized_epub_size: float = 0

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
        old_image_size = sum(rr["old_size"] for rr in self.resize_report)
        new_image_size = sum(rr["new_size"] for rr in self.resize_report)
        compression = round(new_image_size / old_image_size * 100, 2)
        images = len(self.resize_report)
        #errors = len([rr for rr in self.resize_report if rr["error"]])
        return {
            "name": self.original_epub_path.name,
            "time": f"{self.total_time:.2f} s",
            "images": images,
            "old_size": f"{old_image_size / 1024 / 1024:.2f} mb",
            "compressed_to": f"{compression:.2f}%",
            "success": self.resize_success,
        }


@dataclass
class UnpackedEpub:
    original_epub_filepath: Path | None = None
    temporary_directory: Path | None = None
    user_directory: EpubUserDirectory = field(default_factory=EpubUserDirectory)

    file_stats: list[FileStat] = field(default_factory=list)

    chapters: EpubChapters | None = None
    illustrations: EpubIllustrations | None = None


    def _extract(self) -> None:
        if self.original_epub_filepath is None:
            raise ValueError("original_epub_filepath is not set")
        if self.temporary_directory is None:
            self.temporary_directory = Path(tempfile.mkdtemp())
        else:
            self.temporary_directory.mkdir(parents=True, exist_ok=True)
        with ZipFile(self.original_epub_filepath) as zip_file:
            zip_file.extractall(self.temporary_directory)

    def _compact(self, directory: Path) -> Path:
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"UnpackedEpub._compact: directory {directory} does not exist")
        if not self.temporary_directory.exists() or not self.temporary_directory.is_dir():
            raise FileNotFoundError(f"temporary_directory: temporary_directory {self.temporary_directory} does not exist")
        path = directory / self.original_epub_filepath.name
        while path.exists():
            path = path.with_stem(path.stem + "+")
        try:
            with ZipFile(path, "w") as zipf:
                mimetype_file = self.temporary_directory / "mimetype"
                if mimetype_file.exists():
                    zipf.write(mimetype_file, arcname="mimetype", compress_type=ZIP_STORED)
                else:
                    raise FileNotFoundError("Missing required 'mimetype' file for EPUB.")

                for file in self.temporary_directory.rglob("*"):
                    if file.is_file() and file.name != "mimetype":
                        arcname = file.relative_to(self.temporary_directory)
                        zipf.write(file, arcname=arcname, compress_type=ZIP_DEFLATED)
            return path
        except Exception as e:
            logger.error(f"temporary_directory: failed to compress directory into EPUB: {e}")
            raise e
        finally:
            self._teardown()
            
    def _collect_file_stats(self) -> None:
        self.file_stats = [
            FileStat.from_path(filepath, self.temporary_directory)
            for filepath in self.temporary_directory.rglob("*")
            if filepath.is_file()
        ]

    def _teardown(self) -> None:
        if self.temporary_directory and self.temporary_directory.exists():
            shutil.rmtree(self.temporary_directory)
            self.temporary_directory = None

    def file_report(self) -> list[dict]:
        if not self.file_stats:
            self._collect_file_stats()
        
        df = pd.DataFrame([stat.__dict__ for stat in self.file_stats])
        total_size = df["size"].sum()
        
        report = [StatReport(
            name="TOTAL",
            files=len(df),
            size=round(total_size / (1024 * 1024), 2),
            percentage=100.0
        ).to_dict()]
        
        for directory in sorted(df["directory"].unique()):
            dir_data = df[df["directory"] == directory]
            dir_size = dir_data["size"].sum()
            
            report.append(StatReport(
                name=str(directory),
                files=len(dir_data),
                size=round(dir_size / (1024 * 1024), 2),
                percentage=round(dir_size / total_size * 100, 2)
            ).to_dict())
            
            for suffix in sorted(dir_data["suffix"].unique()):
                suffix_data = dir_data[dir_data["suffix"] == suffix]
                suffix_size = suffix_data["size"].sum()
                report.append(StatReport(
                    name=f" {suffix}",
                    files=len(suffix_data),
                    size=round(suffix_size / (1024 * 1024), 2),
                    percentage=round(suffix_size / total_size * 100, 2)
                ).to_dict())
        
        return report

    def optimize(self, image_settings: ImageOptimizationSettings) -> OptimizeResult:
        start_time = time.time()
        result = OptimizeResult()
        result.original_epub_path = self.original_epub_filepath
        result.original_epub_size = self.original_epub_filepath.stat().st_size
        try:
            self._extract()
            self.chapters = EpubChapters(self.temporary_directory)
            self.illustrations = EpubIllustrations(self.temporary_directory, image_settings)
            result.resize_success = self.illustrations.optimize_images()
            result.resize_time = self.illustrations.optimization_time
            if not result.resize_success:
                # WARNING, SOME IMAGES FAILED TO RESIZE
                result.resize_report = self.illustrations.detailed_resize_report()
                result.validation_success = self.illustrations.validate_image_names()
                result.validation_time = self.illustrations.validation_time
            if not result.validation_success:
                # FAIL DUE TO INCORRECT IMAGE RESIZE
                result.validation_report = self.illustrations.validation_report
            result.chapter_success = self.chapters.update_image_references(self.illustrations.get_replacers())
            result.chapter_time = self.chapters.update_time
            if not result.chapter_success:
                # FAIL DUE TO INCORRECT IMAGE REFERENCE UPDATE
                result.chapter_report = self.chapters.detailed_report()
                raise RuntimeError("Failed to update image references")
            # SUCCESS, NO ERRORS
            result.resized_epub_path = self._compact(self.user_directory.resized_dir)
            result.resized_epub_size = result.resized_epub_path.stat().st_size
            result.success = True
        except Exception as e:
            # FAIL DUE TO UNKNOWN ERROR
            result.error = str(e)
            result.success = False
            self._teardown()
        result.total_time = time.time() - start_time
        return result

    def measure_optimized_size(self, image_settings: ImageOptimizationSettings) -> OptimizeResult:
        start_time = time.time()
        result = OptimizeResult()
        result.original_epub_path = self.original_epub_filepath
        result.original_epub_size = self.original_epub_filepath.stat().st_size
        try:
            self._extract()
            self.illustrations = EpubIllustrations(self.temporary_directory, image_settings)
            result.resize_success = self.illustrations.optimize_images()
            result.resize_time = self.illustrations.optimization_time
            result.resize_report = self.illustrations.detailed_resize_report()
            result.success = True
        except Exception as e:
            result.error = str(e)
            result.success = False
        self._teardown()
        result.total_time = time.time() - start_time
        return result


@dataclass
class EpubState:
    """State for EPUB processing"""
    # Paths
    epub_path: Path
    output_path: Path | None = None
    user_directory: EpubUserDirectory = field(default_factory=EpubUserDirectory)

    file_stats: list[FileStat] = field(default_factory=list)

    def move_original(self, directory: Path) -> Path:
        if not self.epub_path.exists() or not directory.exists():
            raise FileNotFoundError(f"EPUBState.move_original: EPUB file {self.epub_path} does not exist")
        path = directory / self.epub_path.name
        while path.exists():
            path = path.with_stem(path.stem + "+")
        self.epub_path.rename(path)
        self.epub_path = path
        return self.epub_path

    def _collect_file_stats(self) -> None:
        with ZipFile(self.epub_path) as zip_file:
            self.file_stats = [
                FileStat.from_zip_info(info)
                for info in zip_file.infolist()
                if not info.is_dir()
            ]