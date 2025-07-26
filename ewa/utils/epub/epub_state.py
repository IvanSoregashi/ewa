from __future__ import annotations

import shutil
import tempfile
import logging
import time

from typing import Any, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pandas as pd

from ewa.utils.epub.image_processor import EpubIllustrations, OptimizeResult, ImageSettings
from ewa.utils.epub.chapter_processor import EpubChapters

logger = logging.getLogger(__name__)


@dataclass
class ZipMixin:
    ziplike_path: Path
    unpacked_directory: Path | None = None
    file_stats: list[FileStat] = field(default_factory=list)

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

    def _collect_file_stats(self) -> None:
        with ZipFile(self.ziplike_path) as zip_file:
            self.file_stats = [
                FileStat.from_zip_info(info)
                for info in zip_file.infolist()
                if not info.is_dir()
            ]

    def iterate(self) -> Iterator[ZipInfo]:
        with ZipFile(self.ziplike_path) as zip_file:
            for info in zip_file.infolist():
                yield info


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
class UnpackedEpub(ZipMixin):
    # Paths
    output_path: Path | None = None
    user_directory: EpubUserDirectory = field(default_factory=EpubUserDirectory)

    chapters: EpubChapters | None = None
    illustrations: EpubIllustrations | None = None

    def _compact_epub(self, directory: Path) -> Path:
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"UnpackedEpub._compact: directory {directory} does not exist")
        if not self.unpacked_directory.exists() or not self.unpacked_directory.is_dir():
            raise FileNotFoundError(f"temporary_directory: temporary_directory {self.unpacked_directory} does not exist")
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

    def _collect_file_stats(self) -> None:
        if not self.unpacked_directory.exists() or not self.unpacked_directory.is_dir():
            super()._collect_file_stats()
        else:
            self.file_stats = [
                FileStat.from_path(filepath, self.unpacked_directory)
                for filepath in self.unpacked_directory.rglob("*")
                if filepath.is_file()
            ]

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

    def optimize(self, image_settings: ImageSettings) -> OptimizeResult:
        start_time = time.time()
        result = OptimizeResult()
        result.original_epub_path = self.ziplike_path
        result.original_epub_size = self.ziplike_path.stat().st_size
        try:
            self._extract()
            self.chapters = EpubChapters(self.unpacked_directory)
            self.illustrations = EpubIllustrations(self.unpacked_directory, image_settings)
            result.optimization_results = self.illustrations.optimize_images()
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
            result.optimization_results = self.illustrations.optimize_images()
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
class Epub(ZipMixin):
    """State for EPUB processing"""
    # Paths
    output_path: Path | None = None
    user_directory: EpubUserDirectory = field(default_factory=EpubUserDirectory)

    def move_original(self, directory: Path) -> Path:
        if not self.ziplike_path.exists() or not directory.exists():
            raise FileNotFoundError(f"EPUBState.move_original: EPUB file {self.ziplike_path} does not exist")
        path = directory / self.ziplike_path.name
        while path.exists():
            path = path.with_stem(path.stem + "+")
        self.ziplike_path.rename(path)
        self.ziplike_path = path
        return self.ziplike_path

