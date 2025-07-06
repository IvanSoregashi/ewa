import json
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
class PipelineData:
    """Minimal data structure passed between pipeline stages"""
    epub_path: Path
    temp_dir: Path
    size_threshold: int
    output_path: Path = None
    file_stats: list[FileStat] = field(default_factory=list)
    resize_results: list[ImageResizeStats] = field(default_factory=list)
    images_to_remove: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def create_epub_data(epub_path: Path, size_threshold: int = 50 * 1024) -> PipelineData:
    """Stage 0: Create EpubData object"""
    if not epub_path.exists() or epub_path.suffix.lower() != '.epub':
        raise FileNotFoundError(f"EPUB file not found: {epub_path}")
    
    return PipelineData(
        epub_path=epub_path,
        temp_dir=Path(tempfile.mkdtemp()),
        size_threshold=size_threshold,
    )


def extract_epub(data: PipelineData) -> PipelineData:
    """Stage 1: Extract EPUB to temporary directory"""
    with ZipFile(data.epub_path) as zip_file:
        zip_file.extractall(data.temp_dir)
    
    return data


def analyze_epub_files(data: PipelineData) -> PipelineData:
    """Stage 2: Analyze files"""
    data.file_stats = [
        FileStat(
            path=filepath,
            size=filepath.stat().st_size,
            suffix=filepath.suffix.lower(),
            name=filepath.stem,
            directory=filepath.parent.relative_to(data.temp_dir)
        )
        for filepath in data.temp_dir.rglob("*")
        if filepath.is_file()
    ]


    
    return data


def generate_static_analytics(data: PipelineData) -> list[StatReport]:
    """Generate static analytics from file statistics"""
    if not data.file_stats:
        logger.warning("generate_static_analytics: no file stats found")
        return []
    
    df = pd.DataFrame([stat.__dict__ for stat in data.file_stats])
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


def generate_resizing_analytics(data: PipelineData) -> list[ImageResizeReport]:
    """Generate resizing analytics in the same format as static analytics"""
    if not data.resize_results:
        return []
    
    results_by_path = {}
    for result in data.resize_results:
        if not result.success:
            continue
        
        directory = result.original_path.parent.relative_to(data.temp_dir)
        suffix = result.original_path.suffix.lower()
        
        if directory not in results_by_path:
            results_by_path[directory] = {}
        if suffix not in results_by_path[directory]:
            results_by_path[directory][suffix] = []
        
        results_by_path[directory][suffix].append(result)
    
    analytics = []
    
    for directory in sorted(results_by_path.keys()):
        dir_results = results_by_path[directory]
        total_files = sum(len(results) for results in dir_results.values())
        large_files = sum(len([r for r in results if r.original_size > data.size_threshold]) 
                         for results in dir_results.values())
        changed_files = sum(len([r for r in results if r.to_save]) 
                           for results in dir_results.values())
        referenced_files = sum(len([r for r in results if r.updated_references > 0]) 
                              for results in dir_results.values())
        orphaned_files = sum(len([r for r in results if r.to_save and r.updated_references == 0]) 
                            for results in dir_results.values())
        total_original_size = sum(r.original_size for results in dir_results.values() 
                                 for r in results)
        total_new_size = sum(r.new_size for results in dir_results.values() 
                            for r in results)
        
        analytics.append(ImageResizeReport(
            name=str(directory),
            files=total_files,
            large_files=large_files,
            changed_files=changed_files,
            referenced_files=referenced_files,
            orphaned_files=orphaned_files,
            original_size_mb=round(total_original_size / (1024 * 1024), 2),
            new_size_mb=round(total_new_size / (1024 * 1024), 2),
            compression_percent=round(total_new_size / total_original_size * 100, 1) if total_original_size > 0 else 100.0
        ))
        
        for suffix in sorted(dir_results.keys()):
            suffix_results = dir_results[suffix]
            suffix_total = len(suffix_results)
            suffix_large = len([r for r in suffix_results if r.original_size > data.size_threshold])
            suffix_changed = len([r for r in suffix_results if r.to_save])
            suffix_referenced = len([r for r in suffix_results if r.updated_references > 0])
            suffix_orphaned = len([r for r in suffix_results if r.to_save and r.updated_references == 0])
            suffix_original_size = sum(r.original_size for r in suffix_results)
            suffix_new_size = sum(r.new_size for r in suffix_results)
            
            analytics.append(ImageResizeReport(
                name=f" {suffix}",
                files=suffix_total,
                large_files=suffix_large,
                changed_files=suffix_changed,
                referenced_files=suffix_referenced,
                orphaned_files=suffix_orphaned,
                original_size_mb=round(suffix_original_size / (1024 * 1024), 2),
                new_size_mb=round(suffix_new_size / (1024 * 1024), 2),
                compression_percent=round(suffix_new_size / suffix_original_size * 100, 1) if suffix_original_size > 0 else 100.0
            ))
    
    return analytics


def display_static_analytics(analytics: list[StatReport]) -> None:
    """Display static analytics in a formatted way"""
    if not analytics:
        print("No analytics data available")
        return
    
    print("\n" + "="*60)
    print("STATIC ANALYTICS")
    print("="*60)
    print(f"{'name':<30} {'count':>8} {'size':>8} {'percent':>8}")
    print("-" * 60)
    
    for item in analytics:
        print(f"{item.name:<30} {item.files:>8} {item.size:>7.1f}MB {item.percentage:>7.1f}%")


def display_resizing_analytics(analytics: list[ImageResizeReport]) -> None:
    """Display resizing analytics in a formatted way"""
    if not analytics:
        print("No resizing analytics data available")
        return
    
    print("\n" + "="*80)
    print("RESIZING ANALYTICS")
    print("="*80)
    print(f"{'name':<30} {'files':>6} {'large':>6} {'changed':>8} {'referenced':>10} {'orphaned':>10} {'original':>10} {'new':>10} {'compression':>10}")
    print("-" * 80)
    
    for item in analytics:
        print(f"{item.name:<30} {item.files:>6} {item.large_files:>6} {item.changed_files:>8} {item.referenced_files:>10} {item.orphaned_files:>10} {item.original_size_mb:>9.1f}MB {item.new_size_mb:>9.1f}MB {item.compression_percent:>9.1f}%")


def resize_images(data: PipelineData, max_workers: int = 50) -> PipelineData:
    """Stage 3: Resize images using threading"""
    image_paths = [
            datum.path
            for datum in data.file_stats
            if datum.directory == Path("EPUB/Images")
            #and datum.size > data.size_threshold
            #and datum.suffix in ('.jpg', '.jpeg', '.png')
        ]
    
    if not image_paths:
        logger.warning("resize_images: no image paths found")
        data.resize_results = []
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            data.resize_results = list(executor.map(_resize_single_image, image_paths))
    return data


def _resize_single_image(image_path: Path, max_width: int = 1080, max_height: int = None, size_threshold: int = 50 * 1024, quality: int = 80) -> ImageResizeStats:
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
            resize_stats.calculate_new_dimensions(max_width, max_height)
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


def update_references(data: PipelineData, max_workers: int = 50) -> PipelineData:
    """Stage 4: Update image references in chapters"""
    
    chapter_paths = [
            datum.path
            for datum in data.file_stats
            if datum.suffix in ('.html', '.xhtml')
            and datum.directory == Path("EPUB/chapters")
        ]
    
    if not chapter_paths or not data.resize_results:
        logger.warning("update_references: no chapter paths or resize results found")
        return data
    
    lock = Lock()
    chapter_tasks = [(chapter_path, data.resize_results, lock)
                     for chapter_path in chapter_paths]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(_update_single_chapter, chapter_tasks))

    return data


def _update_single_chapter(data: tuple[Path, list[ImageResizeStats], Lock]) -> None:
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
                #else:
                #    logger.warning(f"Image {img['src']} not found in resize results")

        chapter_path.write_bytes(soup.prettify(encoding="utf-8"))
        
        with lock:
            for resize_result, count in pending_updates.items():
                resize_result.updated_references += count

    except Exception as e:
        logger.error(f"Error writing chapter {chapter_path}, failure was recorded, {e}")


def package_epub(data: PipelineData) -> PipelineData:
    """Stage 5: Package the modified EPUB"""
    success, target_path = _remove_unused_images(data)
    if success:
        try:
            data.output_path = target_path / data.epub_path.name
            _archive_directory(data.temp_dir, data.output_path)
        except Exception as e:
            logger.error(f"Failed to archive directory: {e}")
    else:
        try:
            data.epub_path.rename(target_path / data.epub_path.name)
        except Exception as e:
            logger.error(f"Failed to move file to {target_path}: {e}")
    
    return data


def _setup_dirs() -> tuple[Path, Path, Path]:
    """
    return quarantine_dir, resized_dir, unchanged_dir
    """
    user_epub_dir = Path("~/Downloads/EPUB").expanduser().absolute()
    quarantine_dir = user_epub_dir / "Quarantine"
    resized_dir = user_epub_dir / "Resized"
    unchanged_dir = user_epub_dir / "Unchanged"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    resized_dir.mkdir(parents=True, exist_ok=True)
    unchanged_dir.mkdir(parents=True, exist_ok=True)
    return quarantine_dir, resized_dir, unchanged_dir


def _remove_unused_images(data: PipelineData) -> tuple[bool, Path]:
    """
    return directory for epub file to be moved to
    """
    quarantine_dir, resized_dir, unchanged_dir = _setup_dirs()
    images_to_remove = []
    for result in data.resize_results:
        if result.success:
            if result.renamed:
                images_to_remove.append(result.original_path)
        else:
            if result.renamed and result.new_path.exists():
                images_to_remove.append(result.new_path)

    if not images_to_remove:
        logger.warning("No unused images to remove, moving file to unchanged directory")
        return False, unchanged_dir
    
    if len(images_to_remove) != len([result for result in data.resize_results if result.renamed]):
        logger.warning(f"Number of images to remove ({len(images_to_remove)}) does not match number of renamed images ({len([result for result in data.resize_results if result.renamed])})")
        return False, quarantine_dir

    for image_path in images_to_remove:
        try:
            image_path.unlink()
        except Exception as e:
            logger.error(f"Error removing {image_path.name}: {e}")
            return False, quarantine_dir
        
    return True, resized_dir


def _archive_directory(source_dir: Path, epub_path: Path) -> None:
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


def create_report(data: PipelineData) -> dict[str, Any]:
    """Stage 6: Generate final processing report"""
    errors = [
        result.error
        for result in data.resize_results
        if result.error
    ]

    if errors:
        return {
            "success": False,
            "errors": errors,
            "epub_path": str(data.epub_path)
        }
    
    static_analytics = generate_static_analytics(data)
    #resizing_analytics = generate_resizing_analytics(data)
    
    return {
        "success": True,
        "epub_path": str(data.epub_path),
        "static_analytics": [report.__dict__ for report in static_analytics],
        #"resizing_analytics": [report.__dict__ for report in resizing_analytics]
    }


def cleanup_stage(data: PipelineData) -> None:
    if data and data.temp_dir and data.temp_dir.exists():
        import shutil
        try:
            shutil.rmtree(data.temp_dir)
            logger.info(f"Cleaned up temporary directory: {data.temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {data.temp_dir}: {e}")


def process_epub_pipeline(epub_path: Path, size_threshold: int = 50 * 1024) -> dict[str, Any]:
    """Main processing pipeline function"""
    data = None
    try:
        data = create_epub_data(epub_path, size_threshold)
        data = extract_epub(data)
        data = analyze_epub_files(data)
        data = resize_images(data)
        data = update_references(data)
        data = package_epub(data)
        return create_report(data)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return {
            "success": False,
            "errors": [str(e)],
            "epub_path": str(epub_path)
        }
    finally:
        cleanup_stage(data)


def analyze_epub_pipeline(epub_path: Path, size_threshold: int = 50 * 1024) -> dict[str, Any]:
    """Analytics-only pipeline function"""
    data = None
    try:
        data = create_epub_data(epub_path, size_threshold)
        data = extract_epub(data)
        data = analyze_epub_files(data)
        data = resize_images(data)
        return create_report(data)
    except Exception as e:
        logger.error(f"Analytics pipeline failed: {e}")
        return {
            "success": False,
            "errors": [str(e)],
            "epub_path": str(epub_path)
        }
    finally:
        cleanup_stage(data)

