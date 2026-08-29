from dataclasses import dataclass, asdict
from enum import IntEnum
from pathlib import Path

from PIL import Image

from library.image.constants import ImageFormat, ImageMode, EFFICIENT_BPP, EXTRA_EFFICIENT_BPP


@dataclass(kw_only=True)
class ImageInfo:
    path: str | None = None
    size: tuple[int, int]
    filesize: int
    format: ImageFormat
    mode: ImageMode
    extrema: tuple[float, float] | tuple[tuple[int, int], ...] | None = None
    is_animated: bool = False
    n_frames: int = 1
    has_transparency_data: bool | None = None
    dpi: tuple[int, int] | None = None
    interlaced: bool | None = None  # png "interlace"
    progressive: bool | None = None  # jpeg "progressive"
    has_exif: bool = False
    has_icc_profile: bool = False

    @classmethod
    def from_image(cls, image: Image.Image, filesize: int) -> ImageInfo:
        info = image.info or {}
        n_frames = getattr(image, "n_frames", 1)

        return cls(
            size=image.size,
            filesize=filesize,
            format=ImageFormat(image.format),
            mode=ImageMode(image.mode),
            is_animated=bool(getattr(image, "is_animated", False)),
            n_frames=int(n_frames),
            has_transparency_data=getattr(image, "has_transparency_data", None),
            dpi=tuple(info["dpi"]) if "dpi" in info else None,
            interlaced=bool(info["interlace"]) if "interlace" in info else None,
            progressive=bool(info.get("progressive") or info.get("progression")),
            has_exif=bool(info.get("exif") or info.get("xmp")),
            has_icc_profile="icc_profile" in info,
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


class ImageSkipReason(IntEnum):
    NOT_OPTIMIZED = 1
    SMALL_IMAGE = 2
    HAS_ANIMATION = 3


class ImageErrorReason(IntEnum):
    DECODE_FAILED = 1  # pixel data unreadable: truncated, corrupt payload
    ENCODE_FAILED = 2  # encoder refused: mode/format mismatch, plugin error
    TOO_LARGE = 3  # decompression limit or memory exhaustion
    UNKNOWN = 4  # unexpected - bug territory


@dataclass(kw_only=True)
class OperationResult:
    success: bool = False
    error: int | None = None
    skip: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(kw_only=True)
class OptimizationResult(OperationResult):
    original_image: ImageInfo
    new_image: ImageInfo | None = None
