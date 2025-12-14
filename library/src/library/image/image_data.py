from PIL import Image
from pathlib import Path
from dataclasses import dataclass


class ImageProcessorError(Exception):
    pass


@dataclass
class ImageData:
    path: Path

    _size: int = 0
    _dimensions: tuple[int, int] = (0, 0)
    _mode: str = ""
    _suffix: str = ""

    _image: Image.Image | None = None

    @property
    def size(self) -> int:
        if not self._size:
            self._size = self.path.stat().st_size if self.path.exists() else 0
        return self._size

    @property
    def dimensions(self) -> tuple[int, int]:
        if self._dimensions == (0, 0):
            self._dimensions = self.image.size
        return self._dimensions

    @dimensions.setter
    def dimensions(self, dimensions: tuple[int, int]) -> None:
        self._dimensions = dimensions

    @property
    def mode(self) -> str:
        if not self._mode:
            self._mode = self.image.mode
        return self._mode

    @mode.setter
    def mode(self, mode: str) -> None:
        self._mode = mode

    @property
    def suffix(self) -> str:
        return self.path.suffix

    @suffix.setter
    def suffix(self, suffix: str) -> None:
        if suffix.lower() != self.path.suffix.lower():
            self.path = self.path.with_suffix(suffix)

    @property
    def image(self) -> Image.Image:
        if not self.path.exists():
            raise FileNotFoundError(f"ImageData.image: image {self.path} does not exist")
        if not self._image:
            try:
                self._image = Image.open(self.path)
            except Exception as e:
                raise ImageProcessorError(f"ImageData.image: error opening image {self.path}: {e}")
        return self._image

    @image.setter
    def image(self, image: Image.Image) -> None:
        self._image = image

    def collect_garbage(self) -> None:
        if self._image is not None:
            self.image.close()
            self.image = None

    def synchronize(self) -> None:
        """Synchronize image data with the settings."""
        if self.image.mode != self.mode:
            self.image = self.image.convert(self.mode)
        if self.image.size != self.dimensions:
            self.image = self.image.resize(self.dimensions, Image.Resampling.LANCZOS)

    def optimize_and_save(self, quality: int = 80) -> None:
        """Optimize image and save to path,
        converting to RGB if necessary,
        resizing if necessary,
        and saving in the correct format."""

        self.synchronize()

        if self.path.suffix.lower() == ".png":
            self.image.save(self.path, optimize=True)
        else:
            self.image.save(self.path, optimize=True, quality=quality)
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
