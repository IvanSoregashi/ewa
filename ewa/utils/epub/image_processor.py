from PIL import Image
import os
import logging
from typing import Generator
import time

from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


logger = logging.getLogger(__name__)


class ImageProcessorError(Exception):
    pass


class NotEligibleError(ImageProcessorError):
    pass


@dataclass
class ImageProcessingResult:
    original_path: Path
    original_size: int

    original_mode: str | None = None
    original_dimensions: tuple[int, int] | None = None

    new_mode: str | None = None
    new_dimensions: tuple[int, int] | None = None

    new_path: Path | None = None
    new_size: int | None = None

    success: bool = False
    error: str = ""
    time: float = 0

    @classmethod
    def from_path(cls, path: Path) -> "ImageProcessingResult":
        size = path.stat().st_size
        return cls(
            original_path=path,
            original_size=size,
            new_path=path,
            new_size=size,
        )

    def update_from_image_header(self, image: Image.Image) -> "ImageProcessingResult":
        self.original_mode = image.mode
        self.original_dimensions = image.size
        self.new_mode = self.original_mode
        self.new_dimensions = self.original_dimensions
        return self

    def update_from_new_path(self) -> "ImageProcessingResult":
        self.new_size = self.new_path.stat().st_size
        return self

    @property
    def name(self) -> str:
        return self.original_path.name

    @property
    def resize_percent(self) -> float:
        if self.original_dimensions and self.new_dimensions:
            return round((self.new_dimensions[0] * self.new_dimensions[1]) / (self.original_dimensions[0] * self.original_dimensions[1]) * 100, 2)
        return 100

    @property
    def compressed_to(self) -> float:
        if self.new_size is None or self.original_size is None:
            return 100
        return round(self.new_size / self.original_size * 100, 2)

    @property
    def savings(self) -> int:
        return self.original_size - self.new_size
    
    @property
    def resized(self) -> bool:
        return self.original_dimensions != self.new_dimensions
    
    @property
    def converted(self) -> bool:
        return self.new_mode == "RGB"

    @property
    def renamed(self) -> bool:
        return self.new_path and self.original_path.name != self.new_path.name

    def short_report(self) -> str:
        pass

    def detailed_report(self) -> str:
        return {
            "name": self.original_path.name,
            "original_mode": self.original_mode,
            "new_mode": self.new_mode,
            "old_size": self.original_size,
            "new_size": self.new_size,
            "resize": self.resize_percent,
            "compressed_to": self.compressed_to,
            "savings": self.savings,
            "error": self.error,
        }


@dataclass
class ImageSettings:
    size_lower_threshold: int = 50 * 1024
    size_upper_threshold: int = 0  # 0 (falsy) means no upper threshold
    supported_suffixes: tuple[str] = ('.jpg', '.jpeg', '.png')
    max_width: int = 1080
    max_height: int = 0  # 0 (falsy) means no upper threshold
    convertible_modes: tuple[str] = ('RGB', 'RGBA')
    quality: int = 80


@dataclass
class ImageProcessor:
    settings: ImageSettings

    def raise_for_suffix(self, result: ImageProcessingResult) -> None:
        if result.original_path.suffix.lower() not in self.settings.supported_suffixes:
            raise NotEligibleError(f"suffix {result.original_path.suffix.lower()} not supported")
        
    def raise_for_size(self, result: ImageProcessingResult) -> None:
        if result.original_size < self.settings.size_lower_threshold:
            raise NotEligibleError(f"size {result.original_size} bytes is too small")
        if self.settings.size_upper_threshold and result.original_size > self.settings.size_upper_threshold:
            raise NotEligibleError(f"size {result.original_size} bytes is too large")
        
    def calculate_new_dimensions(self, result: ImageProcessingResult) -> None:
        width, height = result.original_dimensions
        new_width, new_height = width, height
        if self.settings.max_width and width > self.settings.max_width:
            ratio = self.settings.max_width / width
            new_width = self.settings.max_width
            new_height = int(height * ratio)
        if self.settings.max_height and new_height > self.settings.max_height:
            ratio = self.settings.max_height / new_height
            new_width = int(width * ratio)
            new_height = self.settings.max_height
        result.new_dimensions = (new_width, new_height)

    def calculate_new_mode(self, result: ImageProcessingResult, image: Image.Image) -> None:
        if result.original_mode == 'RGBA':
            # LOADS IMAGE
            extrema = image.getextrema()
            no_transparency = len(extrema) == 4 and extrema[3][0] == 255
            result.new_mode = 'RGB' if no_transparency else 'RGBA'
        else:
            result.new_mode = result.original_mode
    
    def raise_for_mode_and_dimensions(self, result: ImageProcessingResult) -> None:
        if not result.resized and not result.converted:
            raise NotEligibleError(f"mode {result.original_mode} and dimensions {result.original_dimensions} do not need to be processed")

    def calculate_new_path(self, result: ImageProcessingResult) -> None:
        if result.new_mode == 'RGB' and result.original_path.suffix.lower() == '.png':
            result.new_path = result.original_path.with_suffix('.jpg')
        else:
            result.new_path = result.original_path

    def optimize_image(self, path: Path) -> ImageProcessingResult:
        start_time = time.time()
        result = ImageProcessingResult.from_path(path)
        try:
            self.raise_for_suffix(result)
            self.raise_for_size(result)
            with Image.open(path) as image:
                result.update_from_image_header(image)  # reads image header
                self.calculate_new_dimensions(result)
                self.calculate_new_mode(result, image)  # loads image for RGBA
                self.raise_for_mode_and_dimensions(result)
                self.calculate_new_path(result)
                if result.resized:
                    image = image.resize(result.new_dimensions, Image.Resampling.LANCZOS)
                if result.converted:
                    if result.original_mode == 'RGBA':
                        image = image.convert('RGB')
                    image.save(result.new_path, optimize=True, quality=self.settings.quality)
                else:
                    image.save(result.new_path, optimize=True)
                result.update_from_new_path()
                if result.new_size > result.original_size:
                    result.new_path.unlink()
                    result.new_path = result.original_path
                    result.new_size = result.original_size
                    raise NotEligibleError(f"new size {result.new_size} is larger than original size {result.original_size}")
                result.success = True
                if result.renamed:
                    result.original_path.unlink()
        except NotEligibleError as e:
            result.success = True
            result.error = e
        except Exception as e:
            result.success = False
            result.error = e
        result.time = time.time() - start_time
        return result


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

