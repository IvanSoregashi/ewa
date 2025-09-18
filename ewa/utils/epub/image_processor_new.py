from PIL import Image
import os
import logging
from typing import Generator, Protocol
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor


logger = logging.getLogger(__name__)


class ImageProcessorError(Exception):
    pass


@dataclass
class ImageData:
    path: Path
    
    _size: int = 0
    _mode: str = ""
    _dimensions: tuple[int, int] = (0, 0)

    _image: Image.Image | None = None

    @property
    def size(self) -> int:
        if not self._size:
            self._size = self.path.stat().st_size if self.path.exists() else 0
        return self._size

    @property
    def mode(self) -> str:
        if not self._mode:
            self._mode = self.image.mode
        return self._mode

    @mode.setter
    def mode(self, mode: str) -> None:
        self._mode = mode
    
    @property
    def dimensions(self) -> tuple[int, int]:
        if self._dimensions == (0, 0):
            self._dimensions = self.image.size
        return self._dimensions

    @dimensions.setter
    def dimensions(self, dimensions: tuple[int, int]) -> None:
        self._dimensions = dimensions

    @property
    def image(self) -> Image.Image:
        if not self.path.exists():
            raise FileNotFoundError(f"ImageData.image: image {self.path} does not exist")
        if not self._image:
            self._image = Image.open(self.path)
        return self._image

    @image.setter
    def image(self, image: Image.Image) -> None:
        self._image = image

    def collect_garbage(self) -> None:
        self._image.close()
        self._image = None
    
    def optimize_and_save(self, quality: int = 80) -> None:
        """Optimize image and save to path,
        converting to RGB if necessary,
        resizing if necessary,
        and saving in the correct format."""
        if not self._image:
            raise ImageProcessorError(f"ImageData.optimize_and_save: image is not loaded")
        
        if self._image.mode == "RGBA" and self._mode == "RGB":
            self._image = self._image.convert("RGB")
        if self._dimensions != self._image.size:
            self._image = self._image.resize(self._dimensions, Image.Resampling.LANCZOS)
        
        if self.path.suffix.lower() == ".png":
            self._image.save(self.path, optimize=True)
        else:
            self._image.save(self.path, optimize=True, quality=quality)
        self._size = self.path.stat().st_size
        self.collect_garbage()

    def delete_file_if_size_is_same(self) -> bool:
        self.collect_garbage()
        if not self.path.exists():
            return False
        if self.path.stat().st_size == self.size:
            self.path.unlink()
            return True
        return False


@dataclass
class ImageSettings:
    size_lower_threshold: int = 50 * 1024
    size_upper_threshold: int = 0  # 0 (falsy) means no upper threshold
    supported_suffixes: tuple[str] = ('.jpg', '.jpeg', '.png')
    max_width: int = 1080
    max_height: int = 0  # 0 (falsy) means no upper threshold
    quality: int = 80

    def _new_dimensions(self, image: ImageData) -> tuple[int, int]:
        width, height = image.dimensions
        new_width, new_height = width, height
        if self.max_width and width > self.max_width:
            ratio = self.max_width / width
            new_width = self.max_width
            new_height = int(height * ratio)
        if self.max_height and new_height > self.max_height:
            ratio = self.max_height / new_height
            new_width = int(width * ratio)
            new_height = self.max_height
        return (new_width, new_height)

    def _new_mode(self, image: ImageData) -> str:
        if image.mode == 'RGBA':
            extrema = image.image.getextrema()  # LOADS PIXEL DATA
            no_transparency = len(extrema) == 4 and extrema[3][0] == 255
            new_mode = 'RGB' if no_transparency else 'RGBA'
        else:
            new_mode = image.mode
        return new_mode

    def evaluate(self, image: ImageData) -> bool:
        """Returns True if image is eligible for processing, False otherwise."""
        if self.size_lower_threshold and image.size < self.size_lower_threshold:
            return False
        if self.size_upper_threshold and image.size > self.size_upper_threshold:
            return False
        if image.path.suffix.lower() not in self.supported_suffixes:
            return False
        #if image.dimensions[0] < self.max_width or image.dimensions[1] < self.max_height:
        #    return False
        return True

    def construct_new_image(self, image: ImageData) -> ImageData:
        """
        Constructs new image data object.
        image object from original image data object.
        mode and dimensions are configured by settings.
        """
        new_dimensions = self._new_dimensions(image)
        new_mode = self._new_mode(image)
        if new_mode == 'RGB' and image.path.suffix.lower() == '.png':
            new_path = image.path.with_suffix('.jpg')
        else:
            new_path = image.path
        new_image = ImageData(
            path=new_path,
            _mode=new_mode,
            _dimensions=new_dimensions,
            _image=image.image
        )
        return new_image


@dataclass
class ImageProcessingResult:
    ori_image: ImageData
    new_image: ImageData | None = None

    success: bool = False
    error: str = ""
    time: float = 0

    @property
    def name(self) -> str:
        return self.ori_image.path.name

    @property
    def resize_percent(self) -> float:
        o_dim = self.ori_image.dimensions
        n_dim = self.new_image.dimensions if self.new_image else None
        if o_dim and n_dim:
            return round((n_dim[0] * n_dim[1]) / (o_dim[0] * o_dim[1]) * 100, 2)
        return 100

    @property
    def compressed_to(self) -> float:
        if self.new_image.size is None or self.ori_image.size is None:
            return 100
        return round(self.new_image.size / self.ori_image.size * 100, 2)

    @property
    def savings(self) -> int:
        return self.ori_image.size - self.new_image.size
    
    @property
    def resized(self) -> bool:
        return self.ori_image.dimensions != self.new_image.dimensions
    
    @property
    def converted(self) -> bool:
        return self.new_image.mode == "RGB"

    @property
    def renamed(self) -> bool:
        return self.new_image and self.ori_image.path.name != self.new_image.path.name

    def detailed_report(self) -> str:
        return {
            "name": self.name,
            "original_mode": self.ori_image.mode,
            "new_mode": self.new_image.mode,
            "old_size": self.ori_image.size,
            "new_size": self.new_image.size,
            "resize": self.resize_percent,
            "compressed_to": self.compressed_to,
            "savings": self.savings,
            "error": self.error,
        }
    
    def not_eligible_result(self, start_time: float) -> "ImageProcessingResult":
        self.success = True
        self.time = time.time() - start_time
        self.error = "Image is not eligible for processing"
        return self

    def success_result(self, start_time: float, new_image: ImageData) -> "ImageProcessingResult":
        self.success = True
        self.time = time.time() - start_time
        self.new_image = new_image
        return self

    def failure_result(self, start_time: float, error: str) -> "ImageProcessingResult":
        self.ori_image.collect_garbage()
        if self.new_image:
            self.new_image.collect_garbage()
        self.success = False
        self.time = time.time() - start_time
        self.error = error
        return self


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
        return {
            img.name: img.new_image.path.name
            for img in self.optimization_results
            if img.renamed
        }

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
        #errors = len([rr for rr in self.resize_report if rr["error"]])
        return {
            "name": self.original_epub_path.name,
            "time": f"{self.total_time:.2f} s",
            "images": images,
            "old_size": f"{old_image_size / 1024 / 1024:.2f} mb",
            "compressed_to": f"{compression:.2f}%",
            "success": self.optimization_success,
        }


@dataclass
class ImageProcessor:
    settings: ImageSettings

    def optimize_image(self, path: Path) -> ImageProcessingResult:
        start_time = time.time()
        ori_image = ImageData(path)
        eligible = self.settings.evaluate(ori_image)
        result = ImageProcessingResult(ori_image=ori_image)
        if not eligible:
            return result.not_eligible_result(start_time)
        try:
            new_image = self.settings.construct_new_image(ori_image)
            new_image.optimize_and_save(self.settings.quality)
            ori_image.delete_file_if_size_is_same()
            return result.success_result(start_time, new_image)
        except Exception as e:
            return result.failure_result(start_time, str(e))



@dataclass
class EpubIllustrations:
    epub_temp_dir: Path

    image_settings: ImageSettings = field(default_factory=ImageSettings)

    optimization_time: float = 0

    @property
    def actual_size(self) -> int:
        return sum(p.stat().st_size for p in self.iter_image_paths())

    def iter_image_paths(self) -> Generator[Path, None, None]:
        for path in self.epub_temp_dir.glob("EPUB/images/*.*"):
            yield path

    def optimize_images(self) -> list[ImageProcessingResult]:
        start_time = time.time()
        processor = ImageProcessor(self.image_settings)
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            results = list(executor.map(processor.optimize_image, self.iter_image_paths()))
        self.optimization_time = time.time() - start_time
        return results

