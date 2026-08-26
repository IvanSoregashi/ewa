from enum import StrEnum
from pathlib import Path
from typing import Self, override, Any
from library.filetypes import guess_file_type


class FileName(StrEnum):
    MIMETYPE = "mimetype"
    CONTAINER = "META-INF/container.xml"
    DEFAULT_OPF = "content.opf"
    IBOOKS_OPTIONS = "META-INF/com.apple.ibooks.display-options.xml"
    SP_FONT = "fonts/SerenePanda.ttf"
    SP_FONT_LOWER_ENDSWITH = "serenepanda.ttf"


class ManifestId(StrEnum):
    # <item href="nav.xhtml" id="nav" media-type="application/xhtml+xml" properties="nav"/>
    NAV = "nav"
    # <item href="toc.ncx" id="ncx" media-type="application/x-dtbncx+xml"/>
    NCX = "ncx"

    # <meta name="cover" content="cover-img"></meta>
    # <item href="cover.jpg" id="cover-img" media-type="image/jpeg" properties="cover-image"/>
    COVER_IMG = "cover-img"
    # <item href="cover.xhtml" id="cover" media-type="application/xhtml+xml"/>
    COVER = "cover"
    # <item id="title_page" href="OEBPS/title_page.xhtml" media-type="application/xhtml+xml"/>
    TITLE_PAGE = "title_page"
    TITLEPAGE = "titlepage"

    # <item id="style" href="OEBPS/stylesheet.css" media-type="text/css"/>
    STYLE = "style"
    # <item id="page_css" href="page_styles.css" media-type="text/css"/>
    PAGE_CSS = "page_css"
    # <item id="css" href="stylesheet.css" media-type="text/css"/>
    CSS = "css"


class EpubRole(StrEnum):
    MIMETYPE = "MIMETYPE"
    CONTAINER = "CONTAINER"
    OPF = "OPF"
    NCX = "NCX"
    NAV = "NAV"
    XML = "XML"

    STYLE = "STYLE"
    FONT = "FONT"
    SCRIPT = "SCRIPT"

    COVER_IMAGE = "COVER_IMAGE"
    COVER_PAGE = "COVER_PAGE"
    HTML = "HTML"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"

    UNKNOWN = "UNKNOWN"
    GARBAGE = "GARBAGE"

    def is_core(self):
        return (
            self is self.MIMETYPE
            or self is self.CONTAINER
            or self is self.OPF
            or self is self.NCX
            or self is self.NAV
            or self is self.XML
        )

    def is_content(self):
        return self is self.HTML or self is self.IMAGE or self is self.AUDIO or self is self.VIDEO

    def is_common(self):
        return self is self.SCRIPT or self is self.STYLE or self is self.FONT

    def is_other(self):
        return self is self.UNKNOWN or self is self.GARBAGE

    def is_html(self):
        return self is self.HTML or self is self.NAV

    @classmethod
    def from_media_and_path(cls, media_type: MediaType, path: str | Path):
        guessed_role = media_type.guess_role()
        if guessed_role is cls.XML or guessed_role is cls.UNKNOWN:
            if path == FileName.CONTAINER:
                return cls.CONTAINER
            if path == FileName.IBOOKS_OPTIONS:
                return cls.GARBAGE
            if path == FileName.MIMETYPE:
                return cls.MIMETYPE

        return guessed_role

    @classmethod
    def from_id_media_and_path(cls, _id: str, media_type: MediaType, path: str | Path):
        guessed_role = cls.from_media_and_path(media_type=media_type, path=path)
        if _id == ManifestId.NAV:
            return cls.NAV
        if "cover" in _id and media_type.is_image():
            return cls.COVER_IMAGE
        if ("cover" in _id or "title" in _id) and media_type.is_html():
            return cls.COVER_PAGE

        return guessed_role


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

    # Core
    NCX = "application/x-dtbncx+xml"
    OPF = "application/oebps-package+xml"
    XML = "application/xml"

    # Text content
    XHTML = "application/xhtml+xml"
    HTML = "text/html"

    # Images
    IMAGE_GIF = "image/gif"
    IMAGE_JPEG = "image/jpeg"
    IMAGE_PNG = "image/png"
    IMAGE_SVG = "image/svg+xml"
    IMAGE_WEBP = "image/webp"

    # Audio
    AUDIO_MPEG = "audio/mpeg"
    AUDIO_MP4 = "audio/mp4"
    AUDIO_OGG = "audio/ogg"

    # Style
    CSS = "text/css"

    # Fonts
    FONT_TTF = "font/ttf"
    FONT_TTF_OLD = "application/x-font-truetype"
    FONT_OTF = "font/otf"
    FONT_WOFF = "font/woff"
    FONT_WOFF2 = "font/woff2"
    FONT_SFNT = "application/font-sfnt"
    VND_MS_OPENTYPE = "application/vnd.ms-opentype"
    APPLICATION_FONT_WOFF = "application/font-woff"

    # Other
    JAVASCRIPT = "application/javascript"
    ECMASCRIPT = "application/ecmascript"
    TEXT_JAVASCRIPT = "text/javascript"
    SMIL_XML = "application/smil+xml"

    @classmethod
    @override
    def _missing_(cls, value: Any) -> Self:
        if value and isinstance(value, str):
            obj = str.__new__(cls, value)
            obj._value_ = value
            obj._name_ = "FOREIGN"
            cls._value2member_map_[value] = obj
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
        if not guessed:
            guessed = "application/unknown"
        instance = cls(guessed)
        return instance

    @override
    def __str__(self) -> str:
        return self._value_

    def guess_role(self):
        if self.is_html():
            return EpubRole.HTML
        if self is self.XML:
            return EpubRole.XML
        if self.is_image():
            return EpubRole.IMAGE
        if self is self.OPF:
            return EpubRole.OPF
        if self is self.NCX:
            return EpubRole.NCX
        if self.is_video():
            return EpubRole.VIDEO
        if self.is_font():
            return EpubRole.FONT
        if self is self.CSS:
            return EpubRole.STYLE
        if self.is_audio():
            return EpubRole.AUDIO

        return EpubRole.UNKNOWN

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

    def is_js(self) -> bool:
        """Returns whether the media type is javascript."""
        return self is self.JAVASCRIPT or self is self.ECMASCRIPT or self is self.TEXT_JAVASCRIPT

    def is_audio(self) -> bool:
        return self.startswith("audio/")

    def is_video(self) -> bool:
        """Returns whether if the media type is video."""
        return self.startswith("video/")

    def is_image(self) -> bool:
        return (
            self is self.IMAGE_JPEG
            or self is self.IMAGE_PNG
            or self is self.IMAGE_GIF
            or self is self.IMAGE_SVG
            or self is self.IMAGE_WEBP
        )

    def is_font(self) -> bool:
        return (
            self is self.FONT_TTF
            or self is self.FONT_TTF_OLD
            or self is self.FONT_OTF
            or self is self.FONT_WOFF
            or self is self.FONT_WOFF2
            or self is self.FONT_SFNT
            or self is self.VND_MS_OPENTYPE
            or self is self.APPLICATION_FONT_WOFF
        )


def type_and_role_from_filename(filename: str | Path) -> tuple[MediaType, EpubRole]:
    media_type = MediaType.from_filename(filename)
    role = EpubRole.from_media_and_path(media_type, filename)
    return media_type, role


STORE_AS_IS = {
    MediaType.IMAGE_JPEG,
    MediaType.IMAGE_PNG,
    MediaType.IMAGE_GIF,
    MediaType.IMAGE_WEBP,
    MediaType.AUDIO_MPEG,
    MediaType.AUDIO_MP4,
    MediaType.AUDIO_OGG,
}
