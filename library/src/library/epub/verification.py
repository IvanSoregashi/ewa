import io
import random
from zipfile import ZIP_STORED

from lxml import etree

from library.epub.epub import EPUB
from library.epub.protocols import EpubVerification, VerificationResult
from library.epub.media_type import FileName, EpubRole


class MimetypeVerification(EpubVerification):
    """Check that the source contains an uncompressed mimetype entry.

    Checks source archive metadata, not edited output bytes or mimetype contents."""

    def verify(self, epub: EPUB) -> VerificationResult:
        filename = FileName.MIMETYPE
        with epub.keep_open():
            mmt_i = epub.source.getinfo(filename)
            if mmt_i is None:
                return VerificationResult(False, "mimetype file not found")
            if mmt_i.compress_type not in (ZIP_STORED, None):
                return VerificationResult(False, "mimetype file is compressed")
        return VerificationResult(True)


class ValidXMLChapters(EpubVerification):
    """Parse up to count randomly sampled HTML-role resources as XML.

    Reports every malformed document in the sample. Passing a sample does not
    validate unsampled chapters or EPUB semantics; an empty selection passes."""

    def __init__(self, count: int = 10) -> None:
        self.count = count

    def verify(self, epub: EPUB) -> VerificationResult:
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
                return VerificationResult(False, f"{len(failures)}/{count} of {total_chapters}\n" + "\n".join(failures))

        return VerificationResult(True)
