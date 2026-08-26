import logging
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Self
from zipfile import is_zipfile, ZIP_STORED

from library.asserts import require
from library.epub.epub import EPUB
from library.epub.epub_core import EpubCore
from library.epub.resources import ResourceIndex
from library.epub.sink import EpubZipSink
from library.epub.source import DirectorySource, ZipFileSource, SourceProtocol
from library.epub.xml_literals import FileContents
from library.epub.media_type import FileName

logger = logging.getLogger("verification")



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


def verify_mimetype(epub: EPUB) -> bool:
    """Confirm that this source is a valid EPUB by checking the mimetype file.

    Validates:
        1. A file named 'mimetype' exists at the archive root.
        2. Its content is exactly 'application/epub+zip'.
        3. For ZIP sources, it is stored uncompressed (ZIP_STORED).

    Returns:
        True if all checks pass.

    Raises:
        ValueError: If any check fails.
    """
    mmt = FileName.MIMETYPE
    mmt_contents = FileContents.MIMETYPE

    with epub.source.open():
        mimetype_info = epub.source.getinfo(mmt)
        if mimetype_info is None:
            message = f"{epub} is missing the '{mmt!s}' file."
            logger.error(message)
            raise ValueError(message)

        # Check compression: must be ZIP_STORED (0) or None (directory source)
        compress_type = mimetype_info.compress_type
        if compress_type not in (ZIP_STORED, None):
            message = f"{epub} '{mmt!s}' file must be stored uncompressed (ZIP_STORED=0), got {compress_type=}."
            logger.error(message)
            # raise ValueError(message)  # can still work with it

        content = epub.source.read_text(mimetype_info)
        if content.strip() != mmt_contents:
            message = f"{epub} '{mmt!s}' content is not '{mmt_contents!r}', got {content!r}."
            logger.error(message)
            raise ValueError(message)

    return True



def verify_serene_panda_encryption(epub: EPUB) -> bool:
    strict_font = epub.source.getinfo(FileName.SP_FONT)
    return strict_font is not None