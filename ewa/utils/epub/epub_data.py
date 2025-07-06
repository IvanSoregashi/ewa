from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image


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
