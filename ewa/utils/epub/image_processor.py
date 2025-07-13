from PIL import Image
import logging

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from threading import Lock

logger = logging.getLogger(__name__)


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
    size_threshold: int = 50 * 1024
    supported_suffixes: tuple[str] = ('.jpg', '.jpeg', '.png')
    max_width: int = 1080
    max_height: int | None = None
    quality: int = 80

    # References
    success: bool = True
    error: str = ""
    lock: Lock = Lock()
    total_references: int = 0
    updated_references: int = 0


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
    def from_path(cls, path: Path) -> "ImageProcessor":
        size = path.stat().st_size
        return cls(
            original_path=path,
            original_size=size,
            original_mode=None,
            original_dimensions=None,
        )

    @classmethod
    def from_image(cls, path: Path, image: Image.Image) -> "ImageProcessor":
        size = path.stat().st_size
        return cls(
            original_path=path,
            original_size=size,
            original_mode=image.mode,
            original_dimensions=image.size,
            extrema=image.getextrema(),
        )

    def is_eligible(self) -> bool:
        if self.original_size < self.size_threshold:
            self.error = f"{self.original_size} small"
            return False
        if self.original_path.suffix.lower() not in self.supported_suffixes:
            self.error = f"{self.original_path.suffix.lower()} unsupported"
            return False
        return True

    def update_settings(
            self,
            *,
            size_threshold: int | None = None,
            max_width: int | None = None,
            max_height: int | None = None,
            quality: int | None = None,
            supported_suffixes: tuple[str] | None = None,
    ) -> None:
        """
        Update the image resize processor settings.
        Args:
            size_threshold: The size threshold for the image.
            max_width: The maximum width for the image.
            max_height: The maximum height for the image.
            quality: The quality for the image.
            supported_formats: The supported formats for the image.
        """
        if size_threshold is not None:
            self.size_threshold = size_threshold
        if max_width is not None:
            self.max_width = max_width
        if max_height is not None:
            self.max_height = max_height
        if quality is not None:
            self.quality = quality
        if supported_suffixes is not None:
            self.supported_suffixes = supported_suffixes
        
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
        if width > self.max_width:
            ratio = self.max_width / width
            new_width = self.max_width
            new_height = int(height * ratio)
        if self.max_height is not None and new_height > self.max_height:
            ratio = self.max_height / new_height
            new_width = int(width * ratio)
            new_height = self.max_height
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
        if self.original_path.exists():
            self.original_path.unlink()
    
    def _delete_new(self) -> None:
        if self.new_path and self.new_path.exists():
            self.new_path.unlink()

    def optimize_image(self) -> "ImageProcessor":
        if not self.is_eligible():
            return self
        try:
            with Image.open(self.original_path) as image:
                self.update_from_image(image)

                if self.to_resize:
                    image = image.resize(self.new_dimensions, Image.Resampling.LANCZOS)

                if self.to_save:
                    if self.to_convert:
                        image = image.convert('RGB')
                        image.save(self.new_path, optimize=True, quality=self.quality)
                    else:
                        image.save(self.new_path, optimize=True)
                    self.new_size = self.new_path.stat().st_size
        except Exception as e:
            self.success = False
            self.error = f"{e.__class__.__name__}"
        return self

    def threadsafe_increment_total_references(self, amount: int = 1) -> None:
        with self.lock:
            self.total_references += amount

    def threadsafe_increment_updated_references(self, amount: int = 1) -> None:
        with self.lock:
            self.updated_references += amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": str(self.original_path.name)[-10:],
            "new_mode": self.new_mode if self.new_mode == self.original_mode else f"->{self.new_mode}",
            "resize": self.resize_percent,
            "compression": self.compression,
            "renamed": self.renamed,
            "references": self.references_update_status,
            "error": self.error[:50],
        }