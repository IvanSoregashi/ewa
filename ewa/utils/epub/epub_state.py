from __future__ import annotations

import os
import shutil
import tempfile
import logging

from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
from typing import Any, Generator
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ewa.utils.epub.image_processor import ImageProcessor
from ewa.utils.epub.chapter_processor import ChapterProcessor

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
class EpubState:
    """State for EPUB processing"""
    # Paths
    epub_path: Path
    temp_dir: Path | None = None
    output_path: Path | None = None
    user_epub_dir: Path = Path("~/Downloads/EPUB").expanduser().absolute()

    # Filter settings
    size_threshold: int = 50 * 1024
    supported_suffixes: tuple[str] = ('.jpg', '.jpeg', '.png')
    
    # Resize settings
    max_width: int = 1080
    max_height: int | None = None
    quality: int = 80 # 0-100
    workers: int = os.cpu_count()

    # Results
    file_stats: list[FileStat] = field(default_factory=list)
    image_processors: list[ImageProcessor] = field(default_factory=list)
    chapter_results: list[dict[str, Any]] = field(default_factory=list)
    chapter_errors: int = 0
    images_to_remove: list[Path] = field(default_factory=list)
    success: bool = False

    # Target directories
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

    def illustrations(self) -> Generator[Path, None, None]:
        """Generate paths for all illustrations"""
        return (
            datum.path
            for datum in self.file_stats
            if datum.directory == Path("EPUB/Images")
        )
    
    def chapters(self) -> Generator[Path, None, None]:
        """Generate paths for all chapters"""
        return (
            datum.path
            for datum in self.file_stats
            if datum.directory == Path("EPUB/chapters")
        )
    
    def generate_image_processors(self) -> Generator[ImageProcessor, None, None]:
        """Generate image processors for all illustrations"""
        if self.image_processors:
            yield from self.image_processors
        else:
            for path in self.illustrations():
                image_processor = ImageProcessor.from_path(path)
                image_processor.update_settings(
                    size_threshold=self.size_threshold,
                    max_width=self.max_width,
                    max_height=self.max_height,
                    quality=self.quality,
                    supported_suffixes=self.supported_suffixes,
                )
                yield image_processor

    def generate_chapter_processors(self) -> Generator[ChapterProcessor, None, None]:
        """Generate chapter processors for all chapters"""
        for path in self.chapters():
            if path.suffix.lower() not in (".xhtml", ".html"):
                logger.warning(f"chapter_processors: skipping non-HTML file: {path}")
                continue
            chapter_processor = ChapterProcessor(path=path)
            yield chapter_processor

    def __post_init__(self) -> None:
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.resized_dir.mkdir(parents=True, exist_ok=True)
        self.unchanged_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def set_settings(
            self,
            size_threshold: int | None = None, 
            max_width: int | None = None,
            max_height: int | None = None,
            quality: int | None = None, 
            workers: int | None = None,
            supported_suffixes: tuple[str] | None = None
        ) -> None:
        """Set the settings"""
        if size_threshold is not None:
            self.size_threshold = size_threshold
        if max_width is not None:
            self.max_width = max_width
        if max_height is not None:
            self.max_height = max_height
        if quality is not None:
            self.quality = quality
        if workers is not None:
            self.workers = workers
        if supported_suffixes is not None:
            self.supported_suffixes = supported_suffixes

    def extract(self) -> None:
        """
        Extract EPUB to temporary directory
        Updates:
            temp_dir: The temporary directory created or existing.
        """
        if self.temp_dir is None:
            self.temp_dir = Path(tempfile.mkdtemp())
        else:
            self.temp_dir.mkdir(parents=True, exist_ok=True)

        with ZipFile(self.epub_path) as zip_file:
            zip_file.extractall(self.temp_dir)

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

    def resize_illustrations(self) -> None:
        """
        Resize illustrations
        Updates:
            image_processors: The image processors performed the resize.
        """
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            self.image_processors = list(executor.map(lambda ip: ip.optimize_image(), self.generate_image_processors()))

    def resize_report(self) -> list[dict]:
        """
        Generate a report of the resize operations
        """
        return [ip.to_dict() for ip in self.image_processors]

    def update_image_references(self) -> None:
        """
        Update image references
        Updates:
            image_processors: The image processors updated with the number of references.
        """
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            results = list(executor.map(lambda p: p.update_image_references(self.image_processors), self.generate_chapter_processors()))
        success = [result["success"] for result in results]
        if not all(success):
            logger.error(f"EPUBState.update_image_references: success at updating ({sum(success)}/{len(success)})")
        self.chapter_errors = len(success) - sum(success)
        self.chapter_results = results

    def chapter_report(self) -> list[dict]:
        report = []
        for result in self.chapter_results:
            report.append({
                "chapter": result["chapter"],
                "success": result["success"],
                "error": str(result["error"])[:50],
                "renamed": len([i for i, r in result["images"].items() if r == "renamed"]),
                "not_renamed": len([i for i, r in result["images"].items() if r == "not renamed"]),
                "not_found": len([i for i, r in result["images"].items() if r == "not found"]),
            })
        report = [r for r in sorted(report, key=lambda x: x["chapter"])
                  if r["renamed"] or r["not_renamed"] or r["not_found"] or not r["success"]]
        return report

    def remove_unused_images(self) -> tuple[bool, Path]:
        """
        Remove unused images
        Returns:
            True if the images were removed successfully, False otherwise.
            The path to the directory to save epub on success or move to quarantine on failure.
        """
        if self.chapter_errors > 0:
            logger.error(f"EPUBState.remove_unused_images: {self.chapter_errors} chapter errors, moving file to quarantine directory")
            self.success = False

        for image_processor in self.image_processors:
            if image_processor.success and image_processor.renamed and image_processor.references_update_status == "success":
                self.images_to_remove.append(image_processor.original_path)
            if not image_processor.success and image_processor.renamed and image_processor.new_path.exists():
                logger.warning(f"EPUBState.remove_unused_images: image {image_processor.new_path.name} was not resized successfully, removing new path")
                self.images_to_remove.append(image_processor.new_path)
        
        if not self.images_to_remove:
            logger.error("No unused images to remove, moving file to unchanged directory")
            self.success = False
        
        if len(self.images_to_remove) != len([ip for ip in self.image_processors if ip.renamed]):
            logger.error(f"Number of images to remove ({len(self.images_to_remove)}) does not match number of renamed images ({len([ip for ip in self.image_processors if ip.renamed])})")
            self.success = False
        
        for image_path in self.images_to_remove:
            try:
                image_path.unlink()
            except Exception as e:
                logger.error(f"Error removing {image_path.name}: {e}")
                self.success = False
        
        self.success = True
    
    def move_original(self) -> None:
        assert self.epub_path.exists(), f"EPUBState.move_original: EPUB file {self.epub_path} does not exist"
        if self.success:
            path = self.processed_dir / self.epub_path.name
        else:
            path = self.quarantine_dir / self.epub_path.name
        self.epub_path.rename(path)

    def compress_dir_into_epub(self, epub_path: Path | None = None) -> None:
        """
        Compress directory (extracted from EPUB) into EPUB file
        Updates:
            output_path: The EPUB file created.
        """
        if self.success:
            try:
                if epub_path is None:
                    path = self.resized_dir / self.epub_path.name
                else:
                    path = epub_path
                if path.is_dir():
                    path = path / self.epub_path.name
                while path.exists():
                    logger.warning(f"EPUBState.compress_dir_into_epub: file {path} already exists, adding '+'")
                    path = path.with_stem(path.stem + "+")
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
            except Exception as e:
                logger.error(f"EPUBState.compress_dir_into_epub: failed to compress directory into EPUB: {e}")
                self.success = False
        #self.move_original()

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
