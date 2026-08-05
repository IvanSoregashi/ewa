from enum import StrEnum

MEDIUM_WIDTH_SIZE = (1080, 0)
EXTRA_WIDTH_SIZE = (2560, 0)
EFFICIENT_BPP = 0.5
EXTRA_EFFICIENT_BPP = 0.2


class ImageFormat(StrEnum):
    PNG = "PNG"
    JPEG = "JPEG"
    GIF = "GIF"
    BMP = "BMP"
    WEBP = "WEBP"


class ImageMode(StrEnum):
    RGB = "RGB"
    RGBA = "RGBA"
    CMYK = "CMYK"
    L = "L"
    LA = "LA"
    I = "I"
    P = "P"
    ONE = "1"
