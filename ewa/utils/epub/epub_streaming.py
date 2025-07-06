import json
import logging
import tempfile
import pandas as pd
from typing import Any, Callable
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from threading import Lock
from dataclasses import dataclass, field
from functools import partial

from PIL import Image
from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning
import warnings

from ewa.utils.epub.epub_data import FileStat, StatReport, ImageResizeStats, ImageResizeReport

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
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


@dataclass
class ImageResizeStats:
    original_path: Path
    original_size: int
    original_mode: str
    original_dimensions: tuple[int, int]
    extrema: tuple = None
    new_path: Path = None
    new_size: int = 0
    new_mode: str = None
    new_dimensions: tuple[int, int] = None
    success: bool = True
    error: str = None
    total_references: int = 0
    updated_references: int = 0

    @property
    def resize(self) -> float:
        if self.original_dimensions and self.new_dimensions:
            return round((self.original_dimensions[0] * self.original_dimensions[1]) / (self.new_dimensions[0] * self.new_dimensions[1]) * 100, 2)
        return 100

    @property
    def compression(self) -> float:
        return round(self.new_size / self.original_size * 100, 2)

    @property
    def savings(self) -> int:
        return self.original_size - self.new_size

    @property
    def to_resize(self) -> bool:
        return self.original_dimensions != self.new_dimensions
    
    @property
    def to_convert(self) -> bool:
        return self.new_mode == 'RGB'
    
    @property
    def to_save(self) -> bool:
        return self.to_resize or self.to_convert
    
    @property
    def renamed(self) -> bool:
        return self.new_path != self.original_path and self.new_path is not None
    
    @property
    def references_update_status(self) -> str:
        if self.total_references == 0:
            return "orphaned"
        if self.updated_references == 0:
            return "failed"
        if self.updated_references == self.total_references:
            return "success"
        return "partial"

    @classmethod
    def from_image(cls, image_path: Path, image: Image.Image) -> "ImageResizeStats":
        return cls(
            original_path=image_path,
            original_size=image_path.stat().st_size,
            original_mode=image.mode,
            original_dimensions=image.size,
            extrema=image.getextrema(),
        )
    
    def __post_init__(self) -> None:
        self.calculate_new_mode()
        
    def __hash__(self):
        return hash(self.original_path)
    
    def __eq__(self, other):
        if not isinstance(other, ImageResizeStats):
            return False
        return self.original_path == other.original_path

    def calculate_new_dimensions(self, max_width: int = 1080, max_height: int = None) -> None:
        width, height = self.original_dimensions
        new_width, new_height = width, height
        if width > max_width:
            ratio = max_width / width
            new_width = max_width
            new_height = int(height * ratio)
        if max_height is not None and new_height > max_height:
            ratio = max_height / new_height
            new_width = int(width * ratio)
            new_height = max_height
        self.new_dimensions = (new_width, new_height)

    def calculate_new_mode(self) -> None:
        if self.original_mode == 'RGBA':
            assert len(self.extrema) == 4, f"Image of mode RGBA has {self.extrema} extrema"
            self.new_mode = 'RGB' if self.extrema[3][0] == 255 else 'RGBA'
        else:
            self.new_mode = 'RGB' if self.original_mode == 'RGB' else self.original_mode
        self.new_path = self.original_path.with_suffix('.jpg') if self.new_mode == 'RGB' else self.original_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.original_path),
            "old_mode": self.original_mode,
            "new_mode": self.new_mode,
            "resize": self.resize,
            "compression": self.compression,
            "renamed": self.renamed,
            "references": self.references_update_status,
            "error": self.error,
        }


@dataclass
class ImageResizeReport:
    name: str
    files: int
    large_files: int
    changed_files: int
    referenced_files: int
    orphaned_files: int
    original_size_mb: float
    new_size_mb: float
    compression_percent: float


@dataclass
class EpubContentFile:
    """Represents a file within the EPUB archive"""
    path: Path
    size: int
    suffix: str
    name: str
    directory: Path
    content: bytes | None = None


@dataclass
class EpubStreamState:
    """State for streaming EPUB processing"""
    epub_path: Path
    temp_dir: Path | None = None
    output_path: Path | None = None
    size_threshold: int = 50 * 1024
    max_width: int = 1080
    quality: int = 80
    image_workers: int = 50
    chapter_workers: int = 10
    file_stats: list[FileStat] = field(default_factory=list)
    resize_results: list[ImageResizeStats] = field(default_factory=list)
    stream: 'EpubStream' = None


@dataclass
class EpubStream:
    """Stream of EPUB content files with processing capabilities"""
    files: list[EpubContentFile]
    temp_dir: Path
    
    def filter(self, predicate: Callable[[EpubContentFile], bool]) -> 'EpubStream':
        """Filter files based on predicate"""
        filtered_files = [f for f in self.files if predicate(f)]
        return EpubStream(filtered_files, self.temp_dir)
    
    def map(self, func: Callable[[EpubContentFile], Any]) -> list[Any]:
        """Apply function to each file"""
        return [func(f) for f in self.files]
    
    def map_parallel(self, func: Callable[[EpubContentFile], Any], max_workers: int = 10) -> list[Any]:
        """Apply function to each file in parallel"""
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(func, self.files))
    
    def collect(self) -> list[EpubContentFile]:
        """Collect all files"""
        return self.files
    
    def count(self) -> int:
        """Count files in stream"""
        return len(self.files)
    
    def any(self, predicate: Callable[[EpubContentFile], bool]) -> bool:
        """Check if any file matches predicate"""
        return any(predicate(f) for f in self.files)
    
    def all(self, predicate: Callable[[EpubContentFile], bool]) -> bool:
        """Check if all files match predicate"""
        return all(predicate(f) for f in self.files)
    
    def take(self, n: int) -> 'EpubStream':
        """Take first n files"""
        return EpubStream(self.files[:n], self.temp_dir)
    
    def skip(self, n: int) -> 'EpubStream':
        """Skip first n files"""
        return EpubStream(self.files[n:], self.temp_dir)


class EpubStreamProcessor:
    """Streaming processor for EPUB files"""
    
    def __init__(self, epub_path: Path):
        self._state = EpubStreamState(epub_path=epub_path)
    
    def extract(self) -> 'EpubStreamProcessor':
        """Extract EPUB and create file stream"""
        if not self._state.epub_path.exists() or self._state.epub_path.suffix.lower() != '.epub':
            raise FileNotFoundError(f"EPUB file not found: {self._state.epub_path}")
        
        self._state.temp_dir = Path(tempfile.mkdtemp())
        with ZipFile(self._state.epub_path) as zip_file:
            zip_file.extractall(self._state.temp_dir)
        
        # Create file stream and stats
        files = []
        self._state.file_stats = []
        for file_path in self._state.temp_dir.rglob("*"):
            if file_path.is_file():
                epub_content_file = EpubContentFile(
                    path=file_path,
                    size=file_path.stat().st_size,
                    suffix=file_path.suffix.lower(),
                    name=file_path.stem,
                    directory=file_path.parent.relative_to(self._state.temp_dir)
                )
                files.append(epub_content_file)
                
                self._state.file_stats.append(FileStat(
                    path=file_path,
                    size=file_path.stat().st_size,
                    suffix=file_path.suffix.lower(),
                    name=file_path.stem,
                    directory=file_path.parent.relative_to(self._state.temp_dir)
                ))
        
        self._state.stream = EpubStream(files, self._state.temp_dir)
        return self
    
    def process_images(self, size_threshold: int | None = None,
                      max_width: int = 1080, 
                      quality: int = 80,
                      max_workers: int = 50) -> list[ImageResizeStats]:
        """Process images using streaming operations"""
        if not self._state.stream:
            raise ValueError("Must call extract() first")
        
        if size_threshold is not None:
            self._state.size_threshold = size_threshold
        
        # Demonstrate true streaming: chain operations lazily
        self._state.resize_results = (
            self._state.stream
            .filter(is_in_images_dir)           # Filter to images directory
            .filter(is_image)                   # Filter to image files
            .map_parallel(                      # Process in parallel
                partial(self._resize_image, 
                       max_width=max_width, 
                       quality=quality, 
                       size_threshold=self._state.size_threshold),
                max_workers=max_workers
            )
        )
        
        if not self._state.resize_results:
            logger.warning("process_images: no image files found")
        
        return self._state.resize_results
    
    def process_chapters(self, max_workers: int = 10) -> None:
        """Process chapters using streaming operations"""
        if not self._state.stream:
            raise ValueError("Must call extract() first")
        
        if not self._state.resize_results:
            logger.warning("process_chapters: no resize results found")
            return
        
        # Demonstrate streaming for chapter processing
        chapter_stream = (
            self._state.stream
            .filter(is_chapter)                 # Filter to chapter files
            .filter(is_in_chapters_dir)         # Filter to chapters directory
        )
        
        # Process chapters in parallel
        lock = Lock()
        chapter_tasks = [(epub_content_file.path, self._state.resize_results, lock)
                         for epub_content_file in chapter_stream.files]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(self._update_chapter, chapter_tasks))
    
    def package_and_save(self) -> Path | None:
        """Package the modified EPUB"""
        success, target_path = self._remove_unused_images()
        if success:
            try:
                self._state.output_path = target_path / self._state.epub_path.name
                self._archive_directory(self._state.temp_dir, self._state.output_path)
                return self._state.output_path
            except Exception as e:
                logger.error(f"Failed to archive directory: {e}")
                return None
        else:
            try:
                self._state.epub_path.rename(target_path / self._state.epub_path.name)
                return None
            except Exception as e:
                logger.error(f"Failed to move file to {target_path}: {e}")
                return None
    
    def create_report(self) -> dict[str, Any]:
        """Create final report using streaming operations"""
        # Use streaming to analyze results
        error_stream = (
            self._state.stream
            .filter(lambda f: any(r.error for r in self._state.resize_results if r.original_path == f.path))
        )
        
        errors = [
            result.error
            for result in self._state.resize_results
            if result.error
        ]

        if errors:
            return {
                "success": False,
                "errors": errors,
                "epub_path": str(self._state.epub_path)
            }
        
        static_analytics = self._generate_static_analytics()
        
        return {
            "success": True,
            "epub_path": str(self._state.epub_path),
            "output_path": str(self._state.output_path) if self._state.output_path else None,
            "static_analytics": [report.__dict__ for report in static_analytics],
        }
    
    def analyze_stream(self) -> dict[str, Any]:
        """Demonstrate advanced streaming operations"""
        if not self._state.stream:
            raise ValueError("Must call extract() first")
        
        # Demonstrate various streaming operations
        image_count = self._state.stream.filter(is_image).count()
        large_image_count = self._state.stream.filter(is_large_image).count()
        chapter_count = self._state.stream.filter(is_chapter).count()
        
        # Check if any images are in wrong directories
        images_in_wrong_dir = self._state.stream.filter(is_image).filter(
            lambda f: f.directory != Path("EPUB/Images")
        ).count()
        
        # Get file size statistics using streaming
        file_sizes = self._state.stream.map(lambda f: f.size)
        total_size = sum(file_sizes)
        avg_size = total_size / len(file_sizes) if file_sizes else 0
        
        return {
            "total_files": self._state.stream.count(),
            "image_files": image_count,
            "large_images": large_image_count,
            "chapter_files": chapter_count,
            "images_in_wrong_dir": images_in_wrong_dir,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "avg_file_size_kb": round(avg_size / 1024, 2),
            "has_images": self._state.stream.filter(is_image).any(lambda f: True),
            "all_images_in_correct_dir": self._state.stream.filter(is_image).all(
                lambda f: f.directory == Path("EPUB/Images")
            )
        }
    
    def _resize_image(self, epub_content_file: EpubContentFile, max_width: int, quality: int, size_threshold: int) -> ImageResizeStats:
        """Resize a single image"""
        image_path = epub_content_file.path
        suffix = image_path.suffix.lower()
        size = image_path.stat().st_size
        
        if suffix not in ('.jpg', '.jpeg', '.png') or size < size_threshold:
            return ImageResizeStats(
                original_path=image_path,
                original_size=size,
                original_mode=None,
                original_dimensions=None,
                new_size=size,
                success=False,
                error=f"Unsupported image format {suffix} or size ({size} bytes) is below threshold ({size_threshold} bytes), skipping",
            )

        try:
            with Image.open(image_path) as image:
                resize_stats = ImageResizeStats.from_image(image_path, image)
                resize_stats.calculate_new_dimensions(max_width)
                if resize_stats.original_size < size_threshold:
                    resize_stats.success = False
                    resize_stats.error = f"Image is too small, skipping"
                    return resize_stats

                if resize_stats.to_resize:
                    image = image.resize(resize_stats.new_dimensions, Image.Resampling.LANCZOS)
                
                if resize_stats.to_save:
                    if resize_stats.to_convert:
                        image = image.convert('RGB')
                        image.save(resize_stats.new_path, optimize=True, quality=quality)
                    else:
                        image.save(resize_stats.new_path, optimize=True)
                    resize_stats.new_size = resize_stats.new_path.stat().st_size
                else:
                    resize_stats.new_path = resize_stats.original_path
                    resize_stats.new_size = resize_stats.original_size
        except Exception as e:
            resize_stats.success = False
            resize_stats.error = e

        return resize_stats
    
    def _update_chapter(self, data: tuple[Path, list[ImageResizeStats], Lock]) -> None:
        """Update image references in a single chapter"""
        chapter_path, all_results, lock = data
        try:
            soup = BeautifulSoup(chapter_path.read_text(encoding="utf-8"), "lxml")
            pending_updates = defaultdict(int)

            for img in soup.find_all("img"):
                for resize_result in all_results:
                    old_name = resize_result.original_path.name
                    if old_name in img["src"]:
                        with lock:
                            resize_result.total_references += 1
                        
                        if not resize_result.renamed or not resize_result.success:
                            break

                        new_name = resize_result.new_path.name
                        img["src"] = img["src"].replace(old_name, new_name)
                        pending_updates[resize_result] += 1
                        break

            chapter_path.write_bytes(soup.prettify(encoding="utf-8"))
            
            with lock:
                for resize_result, count in pending_updates.items():
                    resize_result.updated_references += count

        except Exception as e:
            logger.error(f"Error writing chapter {chapter_path}, failure was recorded, {e}")
    
    def _remove_unused_images(self) -> tuple[bool, Path]:
        """Remove unused images and return target directory"""
        quarantine_dir, resized_dir, unchanged_dir = self._setup_dirs()
        images_to_remove = []
        
        for result in self.resize_results:
            if result.success:
                if result.renamed:
                    images_to_remove.append(result.original_path)
            else:
                if result.renamed and result.new_path.exists():
                    images_to_remove.append(result.new_path)

        if not images_to_remove:
            logger.warning("No unused images to remove, moving file to unchanged directory")
            return False, unchanged_dir
        
        renamed_count = len([result for result in self.resize_results if result.renamed])
        if len(images_to_remove) != renamed_count:
            logger.warning(f"Number of images to remove ({len(images_to_remove)}) does not match number of renamed images ({renamed_count})")
            return False, quarantine_dir

        for image_path in images_to_remove:
            try:
                image_path.unlink()
            except Exception as e:
                logger.error(f"Error removing {image_path.name}: {e}")
                return False, quarantine_dir
            
        return True, resized_dir
    
    def _setup_dirs(self) -> tuple[Path, Path, Path]:
        """Setup output directories"""
        user_epub_dir = Path("~/Downloads/EPUB").expanduser().absolute()
        quarantine_dir = user_epub_dir / "Quarantine"
        resized_dir = user_epub_dir / "Resized"
        unchanged_dir = user_epub_dir / "Unchanged"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        resized_dir.mkdir(parents=True, exist_ok=True)
        unchanged_dir.mkdir(parents=True, exist_ok=True)
        return quarantine_dir, resized_dir, unchanged_dir
    
    def _archive_directory(self, source_dir: Path, epub_path: Path) -> None:
        """Archive directory to EPUB file"""
        with ZipFile(epub_path, "w") as zipf:
            mimetype_file = source_dir / "mimetype"
            if mimetype_file.exists():
                zipf.write(mimetype_file, arcname="mimetype", compress_type=ZIP_STORED)
            else:
                raise FileNotFoundError("Missing required 'mimetype' file for EPUB.")

            for file in source_dir.rglob("*"):
                if file.is_file() and file.name != "mimetype":
                    arcname = file.relative_to(source_dir)
                    zipf.write(file, arcname=arcname, compress_type=ZIP_DEFLATED)
    
    def _generate_static_analytics(self) -> list[StatReport]:
        """Generate static analytics from file statistics"""
        if not self._state.file_stats:
            logger.warning("generate_static_analytics: no file stats found")
            return []
        
        df = pd.DataFrame([stat.__dict__ for stat in self._state.file_stats])
        total_size = df["size"].sum()
        
        report = [StatReport(
            name="TOTAL",
            files=len(df),
            size=round(total_size / (1024 * 1024), 2),
            percentage=100.0
        )]
        
        for directory in sorted(df["directory"].unique()):
            dir_data = df[df["directory"] == directory]
            dir_size = dir_data["size"].sum()
            
            report.append(StatReport(
                name=str(directory),
                files=len(dir_data),
                size=round(dir_size / (1024 * 1024), 2),
                percentage=round(dir_size / total_size * 100, 2)
            ))
            
            for suffix in sorted(dir_data["suffix"].unique()):
                suffix_data = dir_data[dir_data["suffix"] == suffix]
                suffix_size = suffix_data["size"].sum()
                report.append(StatReport(
                    name=f" {suffix}",
                    files=len(suffix_data),
                    size=round(suffix_size / (1024 * 1024), 2),
                    percentage=round(suffix_size / total_size * 100, 2)
                ))
        
        return report


def process_epub_streaming(epub_path: Path, size_threshold: int = 50 * 1024) -> dict[str, Any]:
    """Main processing function using streaming pattern"""
    processor = None
    try:
        processor = EpubStreamProcessor(epub_path)
        processor.extract()
        processor.process_images(size_threshold)
        processor.process_chapters()
        output_path = processor.package_and_save()
        return processor.create_report()
    except Exception as e:
        logger.error(f"Streaming pipeline failed: {e}")
        return {
            "success": False,
            "errors": [str(e)],
            "epub_path": str(epub_path)
        }
    finally:
        if processor and processor._state.temp_dir and processor._state.temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(processor._state.temp_dir)
                logger.info(f"Cleaned up temporary directory: {processor._state.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {processor._state.temp_dir}: {e}")


def is_image(epub_content_file: EpubContentFile) -> bool:
    """Check if file is an image"""
    return epub_content_file.suffix in ('.jpg', '.jpeg', '.png')


def is_large_image(epub_content_file: EpubContentFile, threshold: int = 50 * 1024) -> bool:
    """Check if file is a large image"""
    return is_image(epub_content_file) and epub_content_file.size > threshold


def is_chapter(epub_content_file: EpubContentFile) -> bool:
    """Check if file is a chapter"""
    return epub_content_file.suffix in ('.html', '.xhtml')


def is_in_images_dir(epub_content_file: EpubContentFile) -> bool:
    """Check if file is in images directory"""
    return epub_content_file.directory == Path("EPUB/Images")


def is_in_chapters_dir(epub_content_file: EpubContentFile) -> bool:
    """Check if file is in chapters directory"""
    return epub_content_file.directory == Path("EPUB/chapters")


def demonstrate_streaming_operations(epub_path: Path) -> dict[str, Any]:
    """Demonstrate various streaming operations on EPUB files"""
    processor = EpubStreamProcessor(epub_path)
    try:
        processor.extract()
        
        # Demonstrate streaming operations
        analysis = processor.analyze_stream()
        
        # Show how streaming can be used for different operations
        print("=== STREAMING DEMONSTRATION ===")
        print(f"Total files: {analysis['total_files']}")
        print(f"Image files: {analysis['image_files']}")
        print(f"Large images: {analysis['large_images']}")
        print(f"Chapter files: {analysis['chapter_files']}")
        print(f"Images in wrong directory: {analysis['images_in_wrong_dir']}")
        print(f"Total size: {analysis['total_size_mb']} MB")
        print(f"Average file size: {analysis['avg_file_size_kb']} KB")
        print(f"Has images: {analysis['has_images']}")
        print(f"All images in correct directory: {analysis['all_images_in_correct_dir']}")
        
        return analysis
        
    except Exception as e:
        logger.error(f"Streaming demonstration failed: {e}")
        return {"error": str(e)}
    finally:
        if processor._state.temp_dir and processor._state.temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(processor._state.temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory: {e}") 