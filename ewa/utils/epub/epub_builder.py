import logging
import tempfile
import pandas as pd

from typing import Any
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from threading import Lock
from dataclasses import dataclass, field

from PIL import Image
from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning
import warnings

from ewa.utils.epub.epub_data import FileStat, StatReport, ImageResizeStats, ImageResizeReport

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
logger = logging.getLogger(__name__)



@dataclass
class EpubBuilderState:
    """Internal state for the builder"""
    epub_path: Path | None = None
    temp_dir: Path | None = None
    output_path: Path | None = None
    size_threshold: int = 50 * 1024
    max_width: int = 1080
    quality: int = 80
    image_workers: int = 50
    chapter_workers: int = 10
    file_stats: list[FileStat] = field(default_factory=list)
    resize_results: list[ImageResizeStats] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class EpubProcessor:
    """Builder pattern implementation for EPUB processing"""
    
    def __init__(self, epub_path: Path):
        self._state = EpubBuilderState(epub_path=epub_path)
    
    def extract(self) -> 'EpubProcessor':
        """Extract EPUB to temporary directory"""
        if not self._state.epub_path.exists() or self._state.epub_path.suffix.lower() != '.epub':
            raise FileNotFoundError(f"EPUB file not found: {self._state.epub_path}")
        
        self._state.temp_dir = Path(tempfile.mkdtemp())
        with ZipFile(self._state.epub_path) as zip_file:
            zip_file.extractall(self._state.temp_dir)
        
        return self
    
    def analyze(self, size_threshold: int | None = None) -> 'EpubProcessor':
        """Analyze files and identify images/chapters"""
        if size_threshold is not None:
            self._state.size_threshold = size_threshold
        
        self._state.file_stats = [
            FileStat(
                path=filepath,
                size=filepath.stat().st_size,
                suffix=filepath.suffix.lower(),
                name=filepath.stem,
                directory=filepath.parent.relative_to(self._state.temp_dir)
            )
            for filepath in self._state.temp_dir.rglob("*")
            if filepath.is_file()
        ]
        
        return self
    
    def resize_images(self, max_width: int | None = None, 
                     quality: int | None = None, 
                     max_workers: int | None = None) -> 'EpubProcessor':
        """Resize images using threading"""
        if max_width is not None:
            self._state.max_width = max_width
        if quality is not None:
            self._state.quality = quality
        if max_workers is not None:
            self._state.image_workers = max_workers
        
        image_paths = [
            datum.path
            for datum in self._state.file_stats
            if datum.directory == Path("EPUB/Images")
        ]
        
        if not image_paths:
            logger.warning("resize_images: no image paths found")
            self._state.resize_results = []
        else:
            with ThreadPoolExecutor(max_workers=self._state.image_workers) as executor:
                self._state.resize_results = list(executor.map(
                    lambda path: self._resize_single_image(path, self._state.max_width, self._state.quality, self._state.size_threshold), 
                    image_paths
                ))
        
        return self
    
    def update_references(self, max_workers: int | None = None) -> 'EpubProcessor':
        """Update image references in chapters"""
        if max_workers is not None:
            self._state.chapter_workers = max_workers
        
        chapter_paths = [
            datum.path
            for datum in self._state.file_stats
            if datum.suffix in ('.html', '.xhtml')
            and datum.directory == Path("EPUB/chapters")
        ]
        
        if not chapter_paths or not self._state.resize_results:
            logger.warning("update_references: no chapter paths or resize results found")
            return self
        
        lock = Lock()
        chapter_tasks = [(chapter_path, self._state.resize_results, lock)
                         for chapter_path in chapter_paths]
        
        with ThreadPoolExecutor(max_workers=self._state.chapter_workers) as executor:
            list(executor.map(self._update_single_chapter, chapter_tasks))
        
        return self
    
    def package(self) -> 'EpubProcessor':
        """Package the modified EPUB"""
        success, target_path = self._remove_unused_images()
        if success:
            try:
                self._state.output_path = target_path / self._state.epub_path.name
                self._archive_directory(self._state.temp_dir, self._state.output_path)
            except Exception as e:
                logger.error(f"Failed to archive directory: {e}")
        else:
            try:
                self._state.epub_path.rename(target_path / self._state.epub_path.name)
            except Exception as e:
                logger.error(f"Failed to move file to {target_path}: {e}")
        
        return self
    
    def report(self, verbose: bool = False) -> dict[str, Any]:
        """Generate final report"""
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
    
    def get_state(self) -> EpubBuilderState:
        """Get the current state"""
        return self._state
    
    def _resize_single_image(self, image_path: Path, max_width: int, quality: int, size_threshold: int) -> ImageResizeStats:
        """Resize a single image - used by ThreadPoolExecutor"""
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
    
    def _update_single_chapter(self, data: tuple[Path, list[ImageResizeStats], Lock]) -> None:
        """Update image references in a single chapter - used by ThreadPoolExecutor"""
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
        
        for result in self._state.resize_results:
            if result.success:
                if result.renamed:
                    images_to_remove.append(result.original_path)
            else:
                if result.renamed and result.new_path.exists():
                    images_to_remove.append(result.new_path)

        if not images_to_remove:
            logger.warning("No unused images to remove, moving file to unchanged directory")
            return False, unchanged_dir
        
        renamed_count = len([result for result in self._state.resize_results if result.renamed])
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


def process_epub_builder(epub_path: Path, size_threshold: int = 50 * 1024) -> dict[str, Any]:
    """Main processing function using builder pattern"""
    processor = None
    try:
        processor = EpubProcessor(epub_path)
        result = (processor
                 .extract()
                 .analyze(size_threshold)
                 .resize_images()
                 .update_references()
                 .package()
                 .report())
        return result
    except Exception as e:
        logger.error(f"Builder pipeline failed: {e}")
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