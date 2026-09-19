"""Per-book working state for sequential plugin recipes."""

from library.asserts import require

from dataclasses import dataclass, field
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self

from sqlmodel import SQLModel

from epub.errors import EpubErrorReason, EpubSkipReason
from epub.protocols import EpubVerification
from epub.results import EpubOperationResult
from library.epub.epub import EPUB, EpubInfo


@dataclass
class _SkipBook(Exception):
    reason: EpubSkipReason
    details: str


@dataclass(kw_only=True)
class ProcessingContext:
    """Use a fresh context for each book and enter it once per recipe call.

    Call open_epub(path) inside the with block so setup failures become outcomes.
    analytics holds unsaved table instances without live resource references.
    Only the parent persists records. Exiting stores result without rollback.
    """

    input_path: Path | None = field(default=None, init=False)
    original_epub: EpubInfo | None = field(default=None, init=False)
    replacements: dict[str, str] = field(default_factory=dict)
    analytics: list[SQLModel] = field(default_factory=list)
    result: EpubOperationResult | None = field(default=None, init=False)
    _epub: EPUB | None = field(default=None, init=False, repr=False)
    _exit_stack: ExitStack = field(init=False, repr=False)
    _new_epub: EpubInfo | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> Self:
        self._exit_stack = ExitStack()
        return self

    def open_epub(self, path: str | Path) -> Self:
        """Open one book and capture original information before editing.

        Register cleanup before reading metadata so even a malformed package
        releases the source. The input path survives failures without more I/O.
        """
        if self.input_path is not None:
            raise RuntimeError("A ProcessingContext can only open one book.")
        self.input_path = Path(path)
        exit_stack = require(self._exit_stack, "ProcessingContext.ExitStack")
        epub = EPUB(path)
        exit_stack.enter_context(epub.keep_open())
        self.original_epub = epub.info()
        self._epub = epub
        return self

    @property
    def epub(self) -> EPUB:
        if self._epub is None:
            raise RuntimeError("Call open_epub(path) before accessing the EPUB.")
        return self._epub

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            self._exit_stack.close()
        except Exception as cleanup_error:
            if exc is not None and not isinstance(exc, Exception):
                # preserving KeyboardInterrupt or SystemExit
                return False
            details = f"Closing EPUB: {cleanup_error!r}"
            if exc is not None:
                details = f"{exc!r}\n{details}"
            self.result = self.outcome(error=EpubErrorReason.UNKNOWN, details=details)
            return True

        if isinstance(exc, _SkipBook):
            self.result = self.outcome(skip=exc.reason, details=exc.details)
        elif isinstance(exc, Exception):
            self.result = self.outcome(error=EpubErrorReason.UNKNOWN, details=repr(exc))
        elif exc is not None:
            # preserving KeyboardInterrupt or SystemExit
            return False
        elif self._new_epub is None:
            self.result = self.outcome(
                error=EpubErrorReason.UNKNOWN, details="Processing ended without succeed(new_info)."
            )
        else:
            self.result = self.outcome(success=True, new_epub=self._new_epub)
        return True

    def verify(self, check: EpubVerification) -> Self:
        """A failed check aborts the with block as a skip.

        Until checks migrate to verify(context), pass the live EPUB to them.
        """
        finding = check.verify(self.epub)
        if not finding.passed:
            raise _SkipBook(check.skip_reason, finding.details)
        return self

    def succeed(self, new_info: EpubInfo) -> None:
        """Mark verified output; a later exception or cleanup failure still wins."""
        if self.original_epub is None:
            raise RuntimeError("Call open_epub(path) before succeed().")
        self._new_epub = new_info

    def outcome(
        self,
        *,
        success: bool = False,
        skip: EpubSkipReason | None = None,
        error: EpubErrorReason | None = None,
        new_epub: EpubInfo | None = None,
        details: str = "",
    ) -> EpubOperationResult:
        """Build a detached outcome without finalizing or changing working state.

        The analytics list is copied; records and book information must not
        be edited after handoff. Live resources and replacements are excluded.
        """
        if sum((success, skip is not None, error is not None)) != 1:
            raise ValueError("Choose exactly one of success, skip, or error.")
        if success and new_epub is None:
            raise ValueError("Success requires new_epub information from the output book.")
        if success and self.original_epub is None:
            raise ValueError("Success requires original_epub information from the input book.")
        return EpubOperationResult(
            success=success,
            skip=skip,
            error=error,
            original_epub=self.original_epub,
            input_path=self.input_path,
            new_epub=new_epub,
            details=details,
            analytics=list(self.analytics),
        )
