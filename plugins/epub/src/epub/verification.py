"""Configured verification steps for plugin recipes.

Checks cover workflow eligibility and selected EPUB/XML conditions; no single
check establishes full publication validity. Failed eligibility checks skip the book.
"""

import io
import json
import random
from zipfile import ZIP_STORED
from lxml import etree
from enum import StrEnum
from epub.processing import ProcessingContext
from epub.protocols import EpubVerification
from epub.errors import EpubSkipReason
from library.epub.media_type import FileName, EpubRole, MediaType


class EpubSpecification(StrEnum):
    UNKNOWN = "UNKNOWN"
    EPUB_MIMETYPE = "EPUB_MIMETYPE"
    EPUB_CONTAINER = "EPUB_CONTAINER"
    SERENE_PANDA_ENCRYPTED = "SERENE_PANDA_ENCRYPTED"
    SERENE_PANDA_DECRYPTED = "SERENE_PANDA_DECRYPTED"
    ASIA_NOVEL = "ASIA_NOVEL"
    CALIBRE = "CALIBRE"
    WEB_TO_EPUB = "WEB_TO_EPUB"
    EPUB_PRESS = "EPUB_PRESS"
    EWA_ONE = "EWA_ONE"


class NoUnmatchedLinks(EpubVerification):
    """Run after ReplaceLinks to reject renames that matched no HTML reference."""

    skip_reason = EpubSkipReason.UNMATCHED_LINKS

    def verify(self, context: ProcessingContext) -> str | None:
        if context.unmatched_links:
            return json.dumps(context.unmatched_links, indent=4)
        return None


class AllResourcesInManifest(EpubVerification):
    skip_reason = EpubSkipReason.UNDECLARED_RESOURCES

    def verify(self, context: ProcessingContext) -> str | None:
        missing = context.epub.package.undeclared_resources
        if missing:
            return "Resources missing from manifest:\n" + "\n".join(resource.filename for resource in missing)
        return None


class SerenePanda(EpubVerification):
    """Check that fonts satisfy the SerenePanda filename condition.

    Requires at least one font. Strict mode requires exactly one font at the
    canonical path; relaxed mode requires every font name to contain the known
    SerenePanda filename. This identifies a candidate book, not valid encryption."""

    skip_reason = EpubSkipReason.SERENE_PANDA_FONT

    def __init__(self, strict: bool = False) -> None:
        self.strict = strict

    def verify(self, context: ProcessingContext) -> str | None:
        epub = context.epub
        strict_filename = FileName.SP_FONT
        filename = FileName.SP_FONT_LOWER_ENDSWITH
        with epub.keep_open():
            fonts = epub.resources.by_role(EpubRole.FONT)

            if not fonts:
                return "SerenePanda font not found"
            if self.strict and len(fonts) != 1:
                return f"Expected exactly one font, found {len(fonts)}"

            for font in fonts:
                if self.strict:
                    if font.filename != strict_filename:
                        return f"Font filename {font.filename!r}, expected {strict_filename!r}"
                else:
                    if filename not in font.filename.lower():
                        return f"Font filename {font.filename!r} does not contain {filename!r}"

        return None


class HasNoGiantGifs(EpubVerification):
    """Check GIF uncompressed sizes against threshold_mb (in MiB).

    Equality passes. Reports every oversized GIF without decoding image pixels."""

    skip_reason = EpubSkipReason.BIG_GIFS

    def __init__(self, threshold_mb: int = 5) -> None:
        self.threshold_mb = threshold_mb

    def verify(self, context: ProcessingContext) -> str | None:
        epub = context.epub
        offenders = []

        with epub.keep_open():
            for gif in epub.resources.by_media_type(MediaType.IMAGE_GIF):
                file_size_mb = gif.info.file_size / (1024 * 1024)
                if file_size_mb > self.threshold_mb:
                    offenders.append(f"{gif.filename!s}: {file_size_mb:.2f} MB")

        if offenders:
            return f"{len(offenders)} offenders found:\n" + "\n".join(offenders)

        return None


class OPFPath(EpubVerification):
    """Check the discovered package resource against expected_path.

    Uses container-based package discovery, so unrelated OPF files do not affect
    the result. Discovery errors propagate instead of passing an empty scan."""

    skip_reason = EpubSkipReason.NON_DEFAULT_OPF

    def __init__(self, expected_path: str = "content.opf") -> None:
        self.expected_path = expected_path

    def verify(self, context: ProcessingContext) -> str | None:
        epub = context.epub
        with epub.keep_open():
            actual_path = epub.package.resource.filename
            if actual_path != self.expected_path:
                return f"Package path {actual_path!r}, expected {self.expected_path!r}"
        return None


class MimetypeVerification(EpubVerification):
    """Check that the source contains an uncompressed mimetype entry.

    Checks source archive metadata, not edited output bytes or mimetype contents."""

    skip_reason = EpubSkipReason.MIMETYPE_VERIFICATION

    def verify(self, context: ProcessingContext) -> str | None:
        epub = context.epub
        filename = FileName.MIMETYPE
        with epub.keep_open():
            mmt_i = epub.source.getinfo(filename)
            if mmt_i is None:
                return "mimetype file not found"
            if mmt_i.compress_type not in (ZIP_STORED, None):
                return "mimetype file is compressed"
        return None


class ValidXMLChapters(EpubVerification):
    """Parse up to count randomly sampled HTML-role resources as XML.

    Reports every malformed document in the sample. Passing a sample does not
    validate unsampled chapters or EPUB semantics; an empty selection passes."""

    skip_reason = EpubSkipReason.INVALID_XML_CHAPTERS

    def __init__(self, count: int = 10) -> None:
        self.count = count

    def verify(self, context: ProcessingContext) -> str | None:
        epub = context.epub
        with epub.keep_open():
            chapters = epub.resources.by_role(EpubRole.HTML)
            total_chapters = len(chapters)
            count = min(self.count, total_chapters)
            sample_chapters = random.sample(chapters.items, count)
            failures = []

            for chapter in sample_chapters:
                try:
                    etree.parse(io.BytesIO(chapter.content), etree.XMLParser(huge_tree=True))
                except etree.XMLSyntaxError as error:
                    failures.append(f"{chapter.filename!r}: {error}")

            if failures:
                return f"{len(failures)}/{count} of {total_chapters}\n" + "\n".join(failures)

        return None
