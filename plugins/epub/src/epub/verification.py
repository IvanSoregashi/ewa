"""Workflow eligibility checks with the shared library verification interface.

These conditions describe this plugin's supported inputs and processing policy,
not general EPUB validity. Findings leave skip decisions to the calling recipe.
"""

from enum import StrEnum
from library.epub.epub import EPUB
from library.epub.protocols import VerificationResult
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


class SerenePanda(EpubVerification):
    """Check that fonts satisfy the SerenePanda filename condition.

    Requires at least one font. Strict mode requires exactly one font at the
    canonical path; relaxed mode requires every font name to contain the known
    SerenePanda filename. This identifies a candidate book, not valid encryption."""

    skip_reason = EpubSkipReason.SERENE_PANDA_FONT

    def __init__(self, strict: bool = False) -> None:
        self.strict = strict

    def verify(self, epub: EPUB) -> VerificationResult:
        strict_filename = FileName.SP_FONT
        filename = FileName.SP_FONT_LOWER_ENDSWITH
        with epub.keep_open():
            fonts = epub.resources.by_role(EpubRole.FONT)

            if not fonts:
                return VerificationResult(False, "SerenePanda font not found")
            if self.strict and len(fonts) != 1:
                return VerificationResult(False, f"Expected exactly one font, found {len(fonts)}")

            for font in fonts:
                if self.strict:
                    if font.filename != strict_filename:
                        return VerificationResult(
                            False, f"Font filename {font.filename!r}, expected {strict_filename!r}"
                        )
                else:
                    if filename not in font.filename.lower():
                        return VerificationResult(
                            False, f"Font filename {font.filename!r} does not contain {filename!r}"
                        )

        return VerificationResult(True)


class HasNoGiantGifs(EpubVerification):
    """Check GIF uncompressed sizes against threshold_mb (in MiB).

    Equality passes. Reports every oversized GIF without decoding image pixels."""

    skip_reason = EpubSkipReason.BIG_GIFS

    def __init__(self, threshold_mb: int = 5) -> None:
        self.threshold_mb = threshold_mb

    def verify(self, epub: EPUB) -> VerificationResult:
        offenders = []

        with epub.keep_open():
            for gif in epub.resources.by_media_type(MediaType.IMAGE_GIF):
                file_size_mb = gif.info.file_size / (1024 * 1024)
                if file_size_mb > self.threshold_mb:
                    offenders.append(f"{gif.filename!s}: {file_size_mb:.2f} MB")

        if offenders:
            return VerificationResult(False, f"{len(offenders)} offenders found:\n" + "\n".join(offenders))

        return VerificationResult(True)


class OPFPath(EpubVerification):
    """Check the discovered package resource against expected_path.

    Uses container-based package discovery, so unrelated OPF files do not affect
    the result. Discovery errors propagate instead of passing an empty scan."""

    skip_reason = EpubSkipReason.NON_DEFAULT_OPF

    def __init__(self, expected_path: str = "content.opf") -> None:
        self.expected_path = expected_path

    def verify(self, epub: EPUB) -> VerificationResult:
        with epub.keep_open():
            actual_path = epub.package.resource.filename
            if actual_path != self.expected_path:
                return VerificationResult(False, f"Package path {actual_path!r}, expected {self.expected_path!r}")
        return VerificationResult(True)
