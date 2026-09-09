import logging
import random
from enum import StrEnum
from zipfile import ZIP_STORED

from lxml import etree

from library.epub.epub import EPUB
from library.epub.errors import EpubSkipReason, EpubErrorReason
from library.epub.protocols import EpubVerification
from library.epub.xml_literals import FileContents
from library.epub.media_type import FileName, EpubRole, MediaType
from library.image.constants import ANIMATION_SIZE_LIMIT

logger = logging.getLogger("verification")

_xml_parser = etree.XMLParser(huge_tree=True)


class EpubSpecification(StrEnum):
    UNKNOWN = "UNKNOWN"
    EPUB_MIMETYPE = "EPUB_MIMETYPE"
    EPUB_CONTAINER = "EPUB_CONTAINER"
    SERENE_PANDA_ENCRYPTED = "SERENE_PANDA_ENCRYPTED"
    SERENE_PANDA_UNENCRYPTED = "SERENE_PANDA_UNENCRYPTED"
    ASIA_NOVEL = "ASIA_NOVEL"
    CALIBRE = "CALIBRE"
    WEB_TO_EPUB = "WEB_TO_EPUB"
    EPUB_PRESS = "EPUB_PRESS"
    EWA_ONE = "EWA_ONE"


class MimetypeVerification(EpubVerification):
    def __init__(self) -> None:
        self.skip = EpubSkipReason.MIMETYPE_VERIFICATION
        self.additional_info = ""
        self.epub_info = None

    def verify(self, epub: EPUB) -> bool:
        filename = FileName.MIMETYPE
        # content = FileContents.MIMETYPE
        with epub.keep_open():
            self.epub_info = epub.info()
            mmt_i = epub.source.getinfo(filename)
            if mmt_i is None:
                self.additional_info = "mimetype file not found"
                return False
            if mmt_i.compress_type not in (ZIP_STORED, None):
                self.additional_info = "mimetype file is compressed"
                return False
            # actual_content = epub.source.read_text(mmt_i)
            # if actual_content != content:
            #     self.additional_info = f"mimetype contents are ({actual_content!s}) instead of ({content!s})"
            #     return False
        return True


class SerenePanda(EpubVerification):
    def __init__(self, strict: bool = False) -> None:
        self.strict = strict
        self.skip = EpubSkipReason.SERENE_PANDA_FONT
        self.additional_info = ""
        self.epub_info = None

    def verify(self, epub: EPUB) -> bool:
        strict_filename = FileName.SP_FONT
        filename = FileName.SP_FONT_LOWER_ENDSWITH
        with epub.keep_open():
            self.epub_info = epub.info()
            fonts = epub.resources.by_role(EpubRole.FONT)

            if self.strict and len(fonts) != 1:
                return False

            for font in fonts:
                if self.strict:
                    if font.filename != strict_filename:
                        self.additional_info = f"font filename - {font.filename}, not {strict_filename}"
                        return False
                else:
                    if filename not in font.filename.lower():
                        self.additional_info = f"font filename - {font.filename}, does not contain {filename}"
                        return False

        return True


class ValidXMLChapters(EpubVerification):
    def __init__(self, count: int = 10) -> None:
        self.count = count
        self.skip = EpubSkipReason.INVALID_XML_CHAPTERS
        self.additional_info = ""
        self.epub_info = None

    def verify(self, epub: EPUB) -> bool:
        with epub.keep_open():
            self.epub_info = epub.info()
            chapters = epub.resources.by_role(EpubRole.HTML)
            total_chapters = len(chapters)
            count = min(self.count, total_chapters)
            sample_chapters = random.sample(chapters.items, count)
            failures = []

            for chapter in sample_chapters:
                try:
                    etree.parse(chapter.content, _xml_parser)
                except etree.XMLSyntaxError as error:
                    failures.append(f"{chapter.filename!r}: {error}")

            if failures:
                self.additional_info = f"{len(failures)}/{count} of {total_chapters}\n" + "\n".join(failures)
                return False

        return True


class HasNoGiantGifs(EpubVerification):
    def __init__(self, threshold_mb: int = 5) -> None:
        self.threshold_mb = threshold_mb
        self.skip = EpubSkipReason.BIG_GIFS
        self.additional_info = ""
        self.epub_info = None

    def verify(self, epub: EPUB) -> bool:
        offenders = []

        with epub.keep_open():
            self.epub_info = epub.info()
            for gif in epub.resources.by_media_type(MediaType.IMAGE_GIF):
                file_size_mb = gif.info.file_size / (1024 * 1024)
                if file_size_mb > self.threshold_mb:
                    offenders.append(f"{gif.filename!s}: {file_size_mb:.2f} MB")

        if offenders:
            self.additional_info = f"{len(offenders)} offenders found:\n" + "\n".join(offenders)
            return False

        return True

class OPFPath(EpubVerification):
    def __init__(self, expected_path: str = "content.opf") -> None:
        self.expected_path = expected_path
        self.skip = EpubSkipReason.NON_DEFAULT_OPF
        self.additional_info = ""
        self.epub_info = None

    def verify(self, epub: EPUB) -> bool:
        with epub.keep_open():
            self.epub_info = epub.info()
            for f in epub.resources.by_role(EpubRole.OPF):
                if f.filename != FileName.DEFAULT_OPF:
                    return False
        return True

