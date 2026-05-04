from enum import StrEnum
from pathlib import Path
from typing import Self, override, Any
import logging
from library.filetypes import guess_file_type

logger = logging.getLogger("media_type")


class ResourceType(StrEnum):
    UNKNOWN = "UNKNOWN"
    CORE = "CORE"
    COMMON = "COMMON"
    CONTENT = "CONTENT"


class Category(StrEnum):
    """
    Broad categories of media types.
    """

    CORE = "CORE"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    MARKUP_CONTENT = "MARKUP_CONTENT"
    STYLE = "STYLE"
    FONT = "FONT"
    OTHER = "OTHER"
    FOREIGN = "FOREIGN"


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
    resource_type: ResourceType

    # Core
    MIMETYPE = "text/mimetype", Category.CORE, ResourceType.CORE
    NCX = "application/x-dtbncx+xml", Category.CORE, ResourceType.CORE
    OPF = "application/oebps-package+xml", Category.CORE, ResourceType.CORE
    XML = "application/xml", Category.CORE, ResourceType.CORE

    # Text content
    XHTML = "application/xhtml+xml", Category.MARKUP_CONTENT, ResourceType.CONTENT
    HTML = "text/html", Category.MARKUP_CONTENT, ResourceType.CONTENT

    # Images
    IMAGE_GIF = "image/gif", Category.IMAGE, ResourceType.CONTENT
    IMAGE_JPEG = "image/jpeg", Category.IMAGE, ResourceType.CONTENT
    IMAGE_PNG = "image/png", Category.IMAGE, ResourceType.CONTENT
    IMAGE_SVG = "image/svg+xml", Category.IMAGE, ResourceType.CONTENT
    IMAGE_WEBP = "image/webp", Category.IMAGE, ResourceType.CONTENT

    # Audio
    AUDIO_MPEG = "audio/mpeg", Category.AUDIO, ResourceType.CONTENT
    AUDIO_MP4 = "audio/mp4", Category.AUDIO, ResourceType.CONTENT
    AUDIO_OGG = "audio/ogg", Category.AUDIO, ResourceType.CONTENT

    # Style
    CSS = "text/css", Category.STYLE, ResourceType.COMMON

    # Fonts
    FONT_TTF = "font/ttf", Category.FONT, ResourceType.COMMON
    FONT_OTF = "font/otf", Category.FONT, ResourceType.COMMON
    FONT_WOFF = "font/woff", Category.FONT, ResourceType.COMMON
    FONT_WOFF2 = "font/woff2", Category.FONT, ResourceType.COMMON
    FONT_SFNT = "application/font-sfnt", Category.FONT, ResourceType.COMMON
    VND_MS_OPENTYPE = "application/vnd.ms-opentype", Category.FONT, ResourceType.COMMON
    APPLICATION_FONT_WOFF = "application/font-woff", Category.FONT, ResourceType.COMMON

    # Other
    JAVASCRIPT = "application/javascript", Category.OTHER, ResourceType.UNKNOWN
    ECMASCRIPT = "application/ecmascript", Category.OTHER, ResourceType.UNKNOWN
    TEXT_JAVASCRIPT = "text/javascript", Category.OTHER, ResourceType.UNKNOWN
    SMIL_XML = "application/smil+xml", Category.OTHER, ResourceType.UNKNOWN

    def __new__(cls, value: str, category: Category, resource_type: ResourceType) -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value

        return obj

    def __init__(
        self,
        value: str,
        category: Category = Category.FOREIGN,
        resource_type: ResourceType = ResourceType.UNKNOWN,
    ) -> None:
        self.category = category
        self.resource_type = resource_type
        super().__init__()

    @classmethod
    @override
    def _missing_(cls, value: Any) -> Self:
        if value and isinstance(value, str):
            obj = str.__new__(cls, value)
            obj._value_ = value
            obj._name_ = "FOREIGN"
            obj.category = Category.FOREIGN
            obj.resource_type = ResourceType.UNKNOWN
            cls._value2member_map_[value] = obj
            logger.warning(f"MediaType - initializing unknown value {value!r}.")
            return obj

        raise ValueError(f"{value} is not a valid {cls.__name__}")

    @classmethod
    def from_filename(cls, value: str | Path) -> Self:
        """
        Detect media type from filename or path. If a mimetype for the
        path is found, but is not supported by MediaType, return it as a string.

        Args:
            value: The file path or name to guess file type from.

        Returns:
            A MediaType instance.
        """
        guessed = guess_file_type(value)
        if value == "mimetype":
            guessed = "text/mimetype"  # custom, idk why
        if not guessed:
            guessed = "application/unknown"
        instance = cls(guessed)
        return instance

    @override
    def __str__(self) -> str:
        return self._value_

    def is_xml(self) -> bool:
        """Returns whether the media type is xml."""
        if self is self.XML or self is self.OPF or self is self.NCX:
            return True
        return False

    def is_html(self) -> bool:
        """Returns whether the media type is html."""
        if self is self.HTML or self is self.XHTML:
            return True
        return False

    def is_css(self) -> bool:
        """Returns whether the media type is CSS."""
        return self is self.CSS

    def is_js(self) -> bool:
        """Returns whether the media type is javascript."""
        return self is self.JAVASCRIPT or self is self.ECMASCRIPT or self is self.TEXT_JAVASCRIPT

    def is_video(self) -> bool:
        """Returns whether if the media type is video."""
        return self.startswith("video/")
