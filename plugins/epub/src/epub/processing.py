"""Per-book working state for sequential plugin recipes."""

from dataclasses import dataclass, field

from sqlmodel import SQLModel

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.protocols import VerificationResult
from epub.results import EpubOperationResult
from library.epub.epub import EPUB, EpubInfo


@dataclass(kw_only=True)
class ProcessingContext:
    """Own working state for one book during one recipe call inside a worker.

    Capture original_epub before editing and run operations sequentially against
    epub. replacements maps old archive paths to new ones, for example
    {"images/cover.png": "images/cover.webp"}; an empty mapping means no work.
    Recipes append check results to findings. Operations may append unsaved
    SQLModel table instances to analytics, but most operations need no record.
    Those records must contain data only, without live EPUB/resource references.
    Only the parent persists records; this context owns no database connection.
    The recipe owns the EPUB/source lifetime and catches execution errors.
    """

    epub: EPUB
    original_epub: EpubInfo
    replacements: dict[str, str] = field(default_factory=dict)
    analytics: list[SQLModel] = field(default_factory=list)
    findings: list[VerificationResult] = field(default_factory=list)

    def outcome(
        self,
        *,
        success: bool = False,
        skip: EpubSkipReason | None = None,
        error: EpubErrorReason | None = None,
        new_epub: EpubInfo | None = None,
        details: str = "",
    ) -> EpubOperationResult:
        """Return exactly one success, skip, or error with accumulated evidence.

        For example, after catching an exception call
        outcome(error=EpubErrorReason.UNKNOWN, details=str(exc)). Earlier
        findings and analytics survive; edits are neither undone nor exported.
        Success requires information captured from the verified output book.
        Lists are copied, while their records and book information are shared;
        stop editing those objects after handing the outcome to the parent.
        The result excludes this context, its EPUB/source, and replacements.
        No persistence, source cleanup, or clearing of working state occurs.
        """
        if sum((success, skip is not None, error is not None)) != 1:
            raise ValueError("Choose exactly one of success, skip, or error.")
        if success and new_epub is None:
            raise ValueError("Success requires new_epub information from the output book.")
        return EpubOperationResult(
            success=success,
            skip=skip,
            error=error,
            original_epub=self.original_epub,
            new_epub=new_epub,
            details=details,
            findings=list(self.findings),
            analytics=list(self.analytics),
        )
