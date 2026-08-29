from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image

from library.image.constants import ImageFormat, ImageMode, EFFICIENT_BPP, EXTRA_EFFICIENT_BPP


@dataclass
class ImageInfo:
    size: tuple[int, int]
    filesize: int
    format: ImageFormat
    mode: ImageMode
    path: str | None = None
    extrema: tuple[float, float] | tuple[tuple[int, int], ...] | None = None

    @classmethod
    def from_image(cls, image: Image.Image, filesize: int) -> ImageInfo:
        return cls(
            size=image.size,
            filesize=filesize,
            format=ImageFormat(image.format),
            mode=ImageMode(image.mode),
        )

    @classmethod
    def from_file(cls, file: Path) -> ImageInfo:
        image = Image.open(file)
        return cls.from_image(image=image, filesize=file.stat().st_size)

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    @property
    def bpp(self) -> float:
        return self.filesize / (self.width * self.height)

    @property
    def is_efficient(self) -> bool:
        return self.bpp < EFFICIENT_BPP

    @property
    def is_extra_efficient(self) -> bool:
        return self.bpp < EXTRA_EFFICIENT_BPP

    @property
    def useless_transparency(self) -> bool:
        return (
            self.extrema is not None
            and self.mode is ImageMode.RGBA
            and len(self.extrema) == 4
            and self.extrema[3][0] == 255
        )


@dataclass(kw_only=True)
class OperationResult:
    success: bool = False
    error: str | None = None
    skip: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(kw_only=True)
class OptimizationResult(OperationResult):
    original_image: ImageInfo
    new_image: ImageInfo | None = None
