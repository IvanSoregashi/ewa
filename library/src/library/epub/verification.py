import logging
import random
from enum import StrEnum
from zipfile import ZIP_STORED

from lxml import etree

from library.epub.epub import EPUB
from library.epub.xml_literals import FileContents
from library.epub.media_type import FileName

logger = logging.getLogger("verification")

CHAPTER_SUFFIXES = (".xhtml", ".html", ".htm")

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


def _parse_xml_stream(epub: EPUB, name: str) -> None:
    """Parse one source entry as XML; raises XMLSyntaxError on invalid content."""
    with epub.source.open_stream(name) as stream:
        etree.parse(stream, _xml_parser)


def verify_chapter_xml(epub: EPUB) -> bool:
    """Confirm that ONE chapter of this EPUB is well-formed XML.

    Fast spot-check: a single randomly chosen chapter is parsed - much cheaper
    than verifying everything. Just `verify_chapters_xml(epub, count=1)`.

    Returns:
        True if the chapter parses as XML.

    Raises:
        ValueError: If the chapter does not parse (with the parser's message),
            or if the EPUB contains no chapter entries at all.
    """
    return verify_chapters_xml(epub, count=1)


def verify_chapters_xml(epub: EPUB, count: int | None = None) -> bool:
    """Confirm that chapters of this EPUB are well-formed XML.

    Source-only and fast: one pass over the archive, one zip handle, chapters
    detected by suffix (.xhtml/.html/.htm), entries parsed with a shared
    parser. Well-formedness only, no DTD/schema validation: void elements must
    be self-closed, tags balanced, a single root element - what epub readers
    and epubcheck require from XHTML content documents. All failures are
    collected - one broken chapter does not hide the rest.

    Args:
        count: verify this many randomly chosen chapters; None (default)
            verifies all. Counts larger than the available chapters verify all.

    Returns:
        True if all (or sampled) chapters parse as XML.

    Raises:
        ValueError: If any verified chapter fails (listing every offending
            entry with its parser message), or if `count` is requested but the
            EPUB contains no chapter entries at all.
    """
    failures: list[str] = []
    with epub.source.open():  # one zip handle for the whole sweep
        chapters = [name for name in epub.source.namelist() if name.lower().endswith(CHAPTER_SUFFIXES)]

        if count is not None:
            if not chapters:
                message = f"{epub}: no chapter entries found"
                logger.error(message)
                raise ValueError(message)
            chapters = random.sample(chapters, min(count, len(chapters)))

        for name in chapters:
            try:
                _parse_xml_stream(epub, name)
            except etree.XMLSyntaxError as error:
                failures.append(f"  {name!r}: {error}")
                logger.error(f"{name!r} is not well-formed XML: {error}")

    if failures:
        message = f"{epub}: {len(failures)} chapter(s) are not well-formed XML:\n" + "\n".join(failures)
        logger.error(message)
        raise ValueError(message)
    return True
