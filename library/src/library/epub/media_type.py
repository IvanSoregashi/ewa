from enum import IntEnum, StrEnum, auto
from pathlib import Path
from typing import Self, override

from library.filetypes import guess_file_type


class Category(IntEnum):
    """
    Broad categories of media types.
    """

    IMAGE = auto()
    """Image-based media (e.g., JPEG, PNG, SVG)."""
    AUDIO = auto()
    """Audio media (e.g., MP3, AAC, OGG)."""
    STYLE = auto()
    """Stylesheets (i.e., CSS)."""
    FONT = auto()
    """Fonts (e.g., OTF, TTF, WOFF)."""
    OTHER = auto()
    """Miscellaneous resources that do not fit in other categories."""
    FOREIGN = auto()
    """Non-core resources."""
    _SENTINEL = auto()


class MediaType(StrEnum):
    """
    An EPUB media type, also known as a MIME type. Core EPUB media types are
    enumerated as members of this class. Non-core media types can be represented
    by instantiating the class with a string value. Example:

    >>> MediaType("image/jpeg")
    <MediaType.IMAGE_JPEG: 'image/jpeg'>
    >>> MediaType("application/unknown")
    <MediaType.FOREIGN: 'application/unknown'>

    Args:
        value (str): The media type string.
    """

    category: Category

    # Images
    IMAGE_GIF = "image/gif", Category.IMAGE
    IMAGE_JPEG = "image/jpeg", Category.IMAGE
    IMAGE_PNG = "image/png", Category.IMAGE
    IMAGE_SVG = "image/svg+xml", Category.IMAGE
    IMAGE_WEBP = "image/webp", Category.IMAGE

    # Audio
    AUDIO_MPEG = "audio/mpeg", Category.AUDIO
    AUDIO_MP4 = "audio/mp4", Category.AUDIO
    AUDIO_OGG = "audio/ogg", Category.AUDIO

    # Style
    CSS = "text/css", Category.STYLE

    # Fonts
    FONT_TTF = "font/ttf", Category.FONT
    FONT_OTF = "font/otf", Category.FONT
    FONT_WOFF = "font/woff", Category.FONT
    FONT_WOFF2 = "font/woff2", Category.FONT
    FONT_SFNT = "application/font-sfnt", Category.FONT
    VND_MS_OPENTYPE = "application/vnd.ms-opentype", Category.FONT
    APPLICATION_FONT_WOFF = "application/font-woff", Category.FONT

    # Other
    TEXT = "text/plain", Category.OTHER
    XHTML = "application/xhtml+xml", Category.OTHER
    JAVASCRIPT = "application/javascript", Category.OTHER
    ECMASCRIPT = "application/ecmascript", Category.OTHER
    TEXT_JAVASCRIPT = "text/javascript", Category.OTHER
    NCX = "application/x-dtbncx+xml", Category.OTHER
    SMIL_XML = "application/smil+xml", Category.OTHER

    def __new__(cls, value: str, category: Category) -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value

        return obj

    def __init__(
        self,
        value: str,
        category: Category = Category._SENTINEL,  # type: ignore[reportPrivateUsage]
    ) -> None:
        self.category = category
        super().__init__()

    @classmethod
    @override
    def _missing_(cls, value: object) -> Self:
        if value and isinstance(value, str):
            obj = str.__new__(cls, value)
            obj._value_ = value
            obj._name_ = "FOREIGN"
            obj.category = Category.FOREIGN
            cls._value2member_map_[value] = obj

            return obj

        raise ValueError(f"{value} is not a valid {cls.__name__}")

    @classmethod
    def from_filename(cls, value: str | Path) -> Self | None:
        """
        Detect media type from filename or path. If a mimetype for the
        path is found, but is not supported by MediaType, return it as a string.

        Args:
            value: The file path or name to guess file type from.

        Returns:
            A MediaType instance if the media type is recognized, None otherwise.
        """

        guessed = guess_file_type(value)
        if not guessed:
            return cls("application/unknown")
        instance = cls(guessed)
        return instance

    @override
    def __str__(self) -> str:
        return self._value_

    def is_css(self) -> bool:
        """Returns whether the media type is CSS."""
        return self is self.CSS

    def is_js(self) -> bool:
        """Returns whether the media type is javascript."""
        return self is self.JAVASCRIPT or self is self.ECMASCRIPT or self is self.TEXT_JAVASCRIPT

    def is_video(self) -> bool:
        """Returns whether if the media type is video."""
        return self.startswith("video/")


IMAGE_MEDIA_TYPES = [
    MediaType.IMAGE_JPEG,
    MediaType.IMAGE_PNG,
    MediaType.IMAGE_SVG,
    "image/jpg",
]
