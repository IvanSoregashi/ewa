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

from ewa.utils.epub.epub_state import EpubState, FileStat, StatReport
from ewa.utils.epub.image_processor import ImageProcessor
from ewa.utils.epub.chapter_processor import ImageResizeReport
from ewa.utils.epub.chapter_processor import compress_dir_into_epub, epub_target_directories

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
logger = logging.getLogger(__name__)

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
class EpubStreamState(EpubState):
    """State for streaming EPUB processing"""
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
                      max_workers: int = 50) -> list[ImageProcessor]:
        """Process images using streaming operations"""
        if not self._state.stream:
            raise ValueError("Must call extract() first")
        
        if size_threshold is not None:
            self._state.size_threshold = size_threshold
        
        # Demonstrate true streaming: chain operations lazily
        self._state.generate_image_processors = (
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
        
        if not self._state.generate_image_processors:
            logger.warning("process_images: no image files found")
        
        return self._state.generate_image_processors
    
    def process_chapters(self, max_workers: int = 10) -> None:
        """Process chapters using streaming operations"""
        if not self._state.stream:
            raise ValueError("Must call extract() first")
        
        if not self._state.generate_image_processors:
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
        chapter_tasks = [(epub_content_file.path, self._state.generate_image_processors, lock)
                         for epub_content_file in chapter_stream.files]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(self._update_chapter, chapter_tasks))
    
    def package_and_save(self) -> Path | None:
        """Package the modified EPUB"""
        success, target_path = self._remove_unused_images()
        if success:
            try:
                self._state.output_path = target_path / self._state.epub_path.name
                compress_dir_into_epub(self._state.temp_dir, self._state.output_path)
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
            .filter(lambda f: any(r.error for r in self._state.generate_image_processors if r.original_path == f.path))
        )
        
        errors = [
            result.error
            for result in self._state.generate_image_processors
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
    
    def _resize_image(self, epub_content_file: EpubContentFile, max_width: int, quality: int, size_threshold: int) -> ImageProcessor:
        """Resize a single image"""
        image_path = epub_content_file.path
        suffix = image_path.suffix.lower()
        size = image_path.stat().st_size
        
        if suffix not in ('.jpg', '.jpeg', '.png') or size < size_threshold:
            return ImageProcessor(
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
                resize_stats = ImageProcessor.from_image(image_path, image)
                resize_stats._calculate_new_dimensions(max_width)
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
    
    def _update_chapter(self, data: tuple[Path, list[ImageProcessor], Lock]) -> None:
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
        quarantine_dir, resized_dir, unchanged_dir = epub_target_directories()
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