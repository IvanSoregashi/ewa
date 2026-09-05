from enum import StrEnum

MEDIUM_WIDTH_SIZE = (1080, 0)
EXTRA_WIDTH_SIZE = (2560, 0)
USELESS_ALPHA_THRESHOLD = 250
EFFICIENT_BPP = 0.5
EXTRA_EFFICIENT_BPP = 0.2

# Animations above this size are converted to MP4 instead of staying GIF
ANIMATION_SIZE_LIMIT = 5 * 1024 * 1024
# ffmpeg crf for the GIF -> MP4 transcode (experiment winner: crf 30)
ANIMATION_CRF = 30


class ImageFormat(StrEnum):
    """All format strings Pillow's plugin registry reports (Image.init()).

    MP4 is the one non-Pillow member: the conversion target for oversized
    animations (see optimization.convert_animation_to_mp4)."""

    MP4 = "MP4"
    AVIF = "AVIF"
    BLP = "BLP"
    BMP = "BMP"
    BUFR = "BUFR"
    CUR = "CUR"
    DCX = "DCX"
    DDS = "DDS"
    DIB = "DIB"
    EPS = "EPS"
    FITS = "FITS"
    FLI = "FLI"
    FTEX = "FTEX"
    GBR = "GBR"
    GIF = "GIF"
    GRIB = "GRIB"
    HDF5 = "HDF5"
    ICNS = "ICNS"
    ICO = "ICO"
    IM = "IM"
    IMT = "IMT"
    IPTC = "IPTC"
    JPEG = "JPEG"
    JPEG2000 = "JPEG2000"
    MCIDAS = "MCIDAS"
    MPO = "MPO"
    MPEG = "MPEG"
    MSP = "MSP"
    PCD = "PCD"
    PCX = "PCX"
    PIXAR = "PIXAR"
    PNG = "PNG"
    PPM = "PPM"
    PSD = "PSD"
    QOI = "QOI"
    SGI = "SGI"
    SPIDER = "SPIDER"
    SUN = "SUN"
    TGA = "TGA"
    TIFF = "TIFF"
    WEBP = "WEBP"
    WMF = "WMF"
    XBM = "XBM"
    XPM = "XPM"
    XVTHUMB = "XVTHUMB"


class ImageMode(StrEnum):
    """All mode strings Pillow's mode registry reports."""

    ONE = "1"
    CMYK = "CMYK"
    F = "F"
    HSV = "HSV"
    I = "I"
    I16 = "I;16"
    I16B = "I;16B"
    I16L = "I;16L"
    I16N = "I;16N"
    L = "L"
    LAB = "LAB"
    LA = "LA"
    LA_LOWER = "La"
    P = "P"
    PA = "PA"
    RGB = "RGB"
    RGBA = "RGBA"
    RGBA_LOWER = "RGBa"
    RGBX = "RGBX"
