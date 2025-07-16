from __future__ import annotations

import os
import shutil
import tempfile
import logging
import time

from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
from typing import Any, Generator
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ewa.utils.epub.image_processor import EpubIllustrations, ImageProcessor
from ewa.utils.epub.chapter_processor import EpubChapters, ChapterProcessor

logger = logging.getLogger(__name__)


@dataclass
class FileStat:
    path: Path
    size: int
    suffix: str
    name: str
    directory: Path


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
    validation_success: bool = False
    validation_time: float = 0
    validation_report: list[dict] = field(default_factory=list)

    # Chapter results
    chapter_success: bool = False
    chapter_time: float = 0
    chapter_report: list[dict] = field(default_factory=list)

    # Total results
    success: bool = False
    total_time: float = 0
    error: str | None = None

    original_epub_path: Path | None = None
    original_epub_size: float = 0
    resized_epub_path: Path | None = None
    resized_epub_size: float = 0

    # Report results
    report_name: str | None = None
    report: list[dict] = field(default_factory=list)

    def report_line_success(self) -> dict:
        return {
            "name": self.original_epub_path.name,
            "time": f"{self.total_time:.2f} s",
            "original_size": f"{self.original_epub_path.stat().st_size / 1024 / 1024:.2f} mb",
            "compression": f"{self.resized_epub_path.stat().st_size / self.original_epub_path.stat().st_size * 100:.2f}%",
        }
    
    def report_line_failure(self) -> dict:
        return {
            "name": self.original_epub_path.name,
            "time": f"{self.total_time:.2f} s",
            "original_size": f"{self.original_epub_path.stat().st_size / 1024 / 1024:.2f} mb",
            "error": self.error[:20] if self.error else "",
        }


@dataclass
class EpubState:
    """State for EPUB processing"""
    # Paths
    epub_path: Path
    temp_dir: Path | None = None
    output_path: Path | None = None
    user_epub_dir: Path = Path("~/Downloads/EPUB").expanduser().absolute()

    # Statistics
    file_stats: list[FileStat] = field(default_factory=list)  # ???

    # Components
    chapters: EpubChapters | None = None
    illustrations: EpubIllustrations | None = None

    @property
    def quarantine_dir(self) -> Path:
        return self.user_epub_dir / "Quarantine"

    @property
    def resized_dir(self) -> Path:
        return self.user_epub_dir / "Resized"

    @property
    def unchanged_dir(self) -> Path:
        return self.user_epub_dir / "Unchanged"

    @property
    def processed_dir(self) -> Path:
        return self.user_epub_dir / "Processed"

    def __post_init__(self) -> None:
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.resized_dir.mkdir(parents=True, exist_ok=True)
        self.unchanged_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def extract(self) -> None:
        """
        Extract EPUB to temporary directory
        Updates:
            temp_dir: The temporary directory created or existing.
            chapters: The chapters component created.
            illustrations: The illustrations component created.
        """
        if self.temp_dir is None:
            self.temp_dir = Path(tempfile.mkdtemp())
        else:
            self.temp_dir.mkdir(parents=True, exist_ok=True)

        with ZipFile(self.epub_path) as zip_file:
            zip_file.extractall(self.temp_dir)
        self.chapters = EpubChapters(self.temp_dir)
        self.illustrations = EpubIllustrations(self.temp_dir)
        
    def collect_file_stats(self) -> None:
        """
        Collect file statistics
        Updates:
            file_stats: The file statistics collected.
        """
        self.file_stats = [
            FileStat(
                path=filepath,
                size=filepath.stat().st_size,
                suffix=filepath.suffix.lower(),
                name=filepath.stem,
                directory=filepath.parent.relative_to(self.temp_dir)
            )
            for filepath in self.temp_dir.rglob("*")
            if filepath.is_file()
        ]

    def file_report(self) -> list[dict]:
        if not self.file_stats:
            logger.warning("generate_static_analytics: no file stats found")
            return []
        
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

    def move_original(self, directory: Path) -> Path:
        if not self.epub_path.exists() or not directory.exists():
            raise FileNotFoundError(f"EPUBState.move_original: EPUB file {self.epub_path} does not exist")
        path = directory / self.epub_path.name
        while path.exists():
            path = path.with_stem(path.stem + "+")
        self.epub_path.rename(path)
        self.epub_path = path
        return self.epub_path

    def compress_dir_into_epub(self, directory: Path) -> Path:
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"EPUBState.compress_dir_into_epub: directory {directory} does not exist")
        if not self.temp_dir.exists() or not self.temp_dir.is_dir():
            raise FileNotFoundError(f"EPUBState.compress_dir_into_epub: temp directory {self.temp_dir} does not exist")
        path = directory / self.epub_path.name
        while path.exists():
            path = path.with_stem(path.stem + "+")
        try:
            with ZipFile(path, "w") as zipf:
                mimetype_file = self.temp_dir / "mimetype"
                if mimetype_file.exists():
                    zipf.write(mimetype_file, arcname="mimetype", compress_type=ZIP_STORED)
                else:
                    raise FileNotFoundError("Missing required 'mimetype' file for EPUB.")

                for file in self.temp_dir.rglob("*"):
                    if file.is_file() and file.name != "mimetype":
                        arcname = file.relative_to(self.temp_dir)
                        zipf.write(file, arcname=arcname, compress_type=ZIP_DEFLATED)
            self.move_original(self.processed_dir)
            return path
        except Exception as e:
            logger.error(f"EPUBState.compress_dir_into_epub: failed to compress directory into EPUB: {e}")
            self.move_original(self.quarantine_dir)
            raise e
            

    def optimize(self) -> OptimizeResult:
        start_time = time.time()
        result = OptimizeResult()
        result.original_epub_path = self.epub_path
        result.original_epub_size = self.epub_path.stat().st_size
        try:
            self.extract()
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
                raise RuntimeError("Failed to validate image failes")
            result.chapter_success = self.chapters.update_image_references(self.illustrations.get_replacers())
            result.chapter_time = self.chapters.update_time
            if not result.chapter_success:
                # FAIL DUE TO INCORRECT IMAGE REFERENCE UPDATE
                result.chapter_report = self.chapters.detailed_report()
                raise RuntimeError("Failed to update image references")
            # SUCCESS, NO ERRORS
            result.resized_epub_path = self.compress_dir_into_epub(self.resized_dir)
            result.success = True
            result.original_epub_path = self.move_original(self.processed_dir)
            result.resized_epub_size = self.resized_epub_path.stat().st_size
        except Exception as e:
            # FAIL DUE TO UNKNOWN ERROR
            result.error = str(e)
            result.success = False
            result.original_epub_path = self.move_original(self.quarantine_dir)
        self.teardown()
        result.total_time = time.time() - start_time
        return result

    def teardown(self) -> None:
        """
        Clean up temporary directory
        Updates:
            temp_dir: The temporary directory deleted.
        """
        logger.warning(f"EPUBState.teardown: cleaning up temporary directory {self.temp_dir}")
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                #logger.error(f"Failed to clean up temporary directory {self.temp_dir}: {e}")
                pass

    def __del__(self) -> None:
        """Destructor - ensures teardown is called when object is garbage collected"""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            self.teardown()
