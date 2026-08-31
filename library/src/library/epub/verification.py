import logging
from enum import StrEnum
from zipfile import ZIP_STORED

from lxml import etree

from library.epub.epub import EPUB
from library.epub.xml_literals import FileContents
from library.epub.media_type import EpubRole, FileName
from library.epub.resources import Resource

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


def verify_chapter_xml(resource: Resource) -> bool:
    """Confirm that a single chapter resource is well-formed XML.

    Well-formedness only (no DTD/schema validation): the document must parse
    with an XML parser - which is what epub readers and epubcheck require from
    XHTML content documents. Void elements must be self-closed, all tags
    balanced, a single root element.

    Returns:
        True if the resource parses as XML.

    Raises:
        ValueError: If the resource does not parse, with the parser's message.
    """
    try:
        etree.fromstring(resource.content)
    except etree.XMLSyntaxError as error:
        message = f"{resource.filename!r} is not well-formed XML: {error}"
        logger.error(message)
        raise ValueError(message) from error
    return True


def verify_chapters_xml(epub: EPUB) -> bool:
    """Confirm that every chapter (HTML-role resource) is well-formed XML.

    All chapters are checked and every failure is collected, so one broken
    chapter does not hide the rest.

    Returns:
        True if all chapters parse as XML.

    Raises:
        ValueError: If any chapter fails, listing every offending filename
            with its parser message.
    """
    failures: list[str] = []
    for resource in epub.resources.by_role(EpubRole.HTML):
        try:
            etree.fromstring(resource.content)
        except etree.XMLSyntaxError as error:
            failures.append(f"  {resource.filename!r}: {error}")
            logger.error(f"{resource.filename!r} is not well-formed XML: {error}")

    if failures:
        message = f"{epub}: {len(failures)} chapter(s) are not well-formed XML:\n" + "\n".join(failures)
        logger.error(message)
        raise ValueError(message)
    return True
