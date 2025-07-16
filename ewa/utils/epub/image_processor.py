from PIL import Image
import os
import logging
from typing import Generator
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)




@dataclass
class ImageOptimizationSettings:
    # Filter settings
    size_threshold: int = 50 * 1024
    supported_suffixes: tuple[str] = ('.jpg', '.jpeg', '.png')
    
    # Resize settings
    max_width: int = 1080
    max_height: int | None = None
    quality: int = 80 # 0-100


@dataclass
class ImageProcessor:
    # Original image
    original_path: Path
    original_size: int
    original_mode: str | None = None
    original_dimensions: tuple[int, int] | None = None

    # New image
    new_path: Path | None = None
    new_size: int = 0
    new_mode: str | None = None
    new_dimensions: tuple[int, int] | None = None

    # Image processing
    extrema: tuple | None = None

    # Settings
    image_settings: ImageOptimizationSettings = field(default_factory=ImageOptimizationSettings)

    # Results
    error: str | None = None

    @property
    def resize_percent(self) -> float:
        if self.original_dimensions and self.new_dimensions:
            return round((self.new_dimensions[0] * self.new_dimensions[1]) / (self.original_dimensions[0] * self.original_dimensions[1]) * 100, 2)
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

    @classmethod
    def from_path(cls, path: Path, settings: ImageOptimizationSettings) -> "ImageProcessor":
        size = path.stat().st_size
        return cls(
            original_path=path,
            original_size=size,
            original_mode=None,
            original_dimensions=None,
            image_settings=settings,
        )

    @classmethod
    def from_image(cls, path: Path, image: Image.Image, settings: ImageOptimizationSettings) -> "ImageProcessor":
        size = path.stat().st_size
        return cls(
            original_path=path,
            original_size=size,
            original_mode=image.mode,
            original_dimensions=image.size,
            extrema=image.getextrema(),
            image_settings=settings,
        )

    def update_from_image(self, image: Image.Image) -> None:
        """
        Update the image resize processor from a PIL image.
        Args:
            image: The PIL image to update from.
        Updates:
        - original_mode
        - original_dimensions
        - extrema
        - new_mode
        - new_dimensions
        - new_size
        - new_path
        """
        self.original_mode = image.mode
        self.original_dimensions = image.size
        self.extrema = image.getextrema()
        self.__post_init__()

    def __post_init__(self) -> None:
        """
        Post-initialization method.
        Updates:
        - new_mode
        - new_dimensions
        - new_size
        - new_path
        """
        self._calculate_new_mode()
        self.new_path = self.original_path.with_suffix('.jpg') if self.new_mode == 'RGB' else self.original_path
        self.new_size = self.original_size
        self._calculate_new_dimensions()

    def not_eligible(self) -> None:
        self.new_path = self.original_path
        self.new_size = self.original_size
        self.new_mode = self.original_mode
        self.new_dimensions = self.original_dimensions

    def is_eligible(self) -> bool:
        if self.original_size < self.image_settings.size_threshold:
            self.error = f"{self.original_size} small"
            return False
        if self.original_path.suffix.lower() not in self.image_settings.supported_suffixes:
            self.error = f"{self.original_path.suffix.lower()} unsupported"
            return False
        return True

    def __hash__(self):
        return hash(self.original_path)

    def __eq__(self, other):
        if not isinstance(other, ImageProcessor):
            return False
        return self.original_path == other.original_path

    def _calculate_new_dimensions(self) -> None:
        """
        Calculate the new dimensions for the image.
        Updates:
            new_dimensions: The new dimensions for the image.
        """
        if self.original_dimensions is None:
            self.new_dimensions = None
            return
        width, height = self.original_dimensions
        new_width, new_height = width, height
        if width > self.image_settings.max_width:
            ratio = self.image_settings.max_width / width
            new_width = self.image_settings.max_width
            new_height = int(height * ratio)
        if self.image_settings.max_height is not None and new_height > self.image_settings.max_height:
            ratio = self.image_settings.max_height / new_height
            new_width = int(width * ratio)
            new_height = self.image_settings.max_height
        self.new_dimensions = (new_width, new_height)

    def _calculate_new_mode(self) -> None:
        """
        Calculate the new mode for the image.
        Updates:
            new_mode: The new mode for the image.
        """
        if self.original_mode == 'RGBA':
            assert len(self.extrema) == 4, f"Image of mode RGBA has {self.extrema} extrema"
            self.new_mode = 'RGB' if self.extrema[3][0] == 255 else 'RGBA'
        else:
            self.new_mode = 'RGB' if self.original_mode == 'RGB' else self.original_mode

    def _delete_original(self) -> None:
        if self.renamed and self.original_path.exists() and self.new_path.exists():
            self.original_path.unlink()
    
    def _delete_new(self) -> None:
        if self.renamed and self.original_path.exists() and self.new_path.exists():
            self.new_path.unlink()

    def optimize_image(self) -> bool:
        if not self.is_eligible():
            self.not_eligible()
            return True
        try:
            with Image.open(self.original_path) as image:
                self.update_from_image(image)

                if self.to_resize:
                    image = image.resize(self.new_dimensions, Image.Resampling.LANCZOS)

                if self.to_save:
                    if self.to_convert:
                        image = image.convert('RGB')
                        image.save(self.new_path, optimize=True, quality=self.image_settings.quality)
                    else:
                        image.save(self.new_path, optimize=True)
                    self.new_size = self.new_path.stat().st_size
                    self._delete_original()
                else:
                    self.error = f"not eligible: {self.original_mode} {self.original_dimensions}"
                    self.not_eligible()
            return True
        except Exception as e:
            self.error = f"{e.__class__.__name__}"
            self._delete_new()
            self.not_eligible()
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": str(self.original_path.name)[-10:],
            "new_mode": self.new_mode if self.new_mode == self.original_mode else f"->{self.new_mode}",
            "resize": self.resize_percent,
            "compression": self.compression,
            "error": self.error[:20] if self.error else "",
        }
    

@dataclass
class EpubIllustrations:
    epub_temp_dir: Path
    image_processors: list[ImageProcessor] = field(default_factory=list)

    image_settings: ImageOptimizationSettings = field(default_factory=ImageOptimizationSettings)

    optimization_time: float = 0
    validation_time: float = 0
    validation_report: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.image_processors = list(self.iter_image_processors())

    def __len__(self) -> int:
        return len(self.image_processors)

    @property
    def original_size(self) -> int:
        return sum(ip.original_size for ip in self.image_processors)

    @property
    def actual_size(self) -> int:
        return sum(p.stat().st_size for p in self.iter_image_paths())

    @property
    def new_size(self) -> int:
        return sum(ip.new_size for ip in self.image_processors)

    @property
    def compression(self) -> float:
        return round(self.new_size / self.original_size * 100, 2)

    @property
    def errors(self) -> list[str]:
        return [ip.error for ip in self.image_processors if ip.error is not None]
    
    @property
    def errors_count(self) -> int:
        return len(self.errors)

    def iter_image_paths(self) -> Generator[Path, None, None]:
        for path in self.epub_temp_dir.glob("EPUB/images/*.*"):
            yield path

    def iter_image_processors(self) -> Generator[ImageProcessor, None, None]:
        for path in self.iter_image_paths():
            processor = ImageProcessor.from_path(path, self.image_settings)
            yield processor

    def optimize_images(self) -> bool:
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            results = executor.map(ImageProcessor.optimize_image, self.image_processors)
        self.optimization_time = time.time() - start_time
        return all(results)

    def get_replacers(self) -> dict[str, str]:
        return {
            img.original_path.name: img.new_path.name
            for img in self.image_processors
            if img.renamed
        }
    
    def short_report(self) -> str:
        return f"{self.original_size() / 1024 / 1024:.2f} mb / {len(self)}"

    def short_optimization_report(self) -> str:
        return {
            "images t/o/e": f"{len(self)} / {len([ip for ip in self.image_processors if ip.error is None])} / {self.errors_count}",
            "compression": f"{self.compression:.2f}%",
            "time": f"{self.optimization_time:.2f} s",
        }

    def detailed_resize_report(self) -> str:
        return [ip.to_dict() for ip in self.image_processors]

    def validate_image_names(self) -> bool:
        start_time = time.time()
        
        data_names = [ip.new_path.name if ip.renamed else ip.original_path.name
                    for ip in self.image_processors]
        real_names = [path.name for path in self.iter_image_paths()]
        data_names = list(sorted(data_names))
        real_names = list(sorted(real_names))

        #data_paths = [ip.new_path if ip.renamed else ip.original_path
        #              for ip in self.image_processors]
        #exist = all(path.exists() for path in data_paths)
        #real_paths = [path for path in self.iter_image_paths()]
        #data_paths = list(sorted(data_paths))
        #real_paths = list(sorted(real_paths))

        if data_names == real_names:
            self.validation_time = time.time() - start_time
            return True
        else:
            names_diff = set(data_names) ^ set(real_names)
            self.validation_report = {
                "names_diff": names_diff,
                "len_real": len(real_names),
                "len_data": len(data_names),
            }
            logger.error(f"dn len={len(data_names)}, rn len={len(real_names)}, diff={names_diff=}")
            self.validation_time = time.time() - start_time
            return False
    
